"""Adversarial contracts for the private Market Memory W1B.0 source store."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, ValidationError

from app import market_memory as market_memory_api
from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_sources as sources

ROOT = Path(__file__).resolve().parents[1]
OBSERVED_AT = "2025-02-13T00:03:00Z"


def _set_source_clock(monkeypatch: pytest.MonkeyPatch, stamp: str) -> None:
    value = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    monkeypatch.setattr(sources, "_utc_now", lambda: value)


@pytest.fixture(autouse=True)
def _fixed_source_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_source_clock(monkeypatch, OBSERVED_AT)


def _matrix(*, latest_value: float = 111.1) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "series": "CPIAUCSL",
                "period": "2024-12-01",
                "realtime_start": "2025-01-15",
                "realtime_end": "2025-02-11",
                "value": 100.0,
                "source_output_type": 2,
            },
            {
                "series": "CPIAUCSL",
                "period": "2024-12-01",
                "realtime_start": "2025-02-12",
                "realtime_end": "9999-12-31",
                "value": 110.0,
                "source_output_type": 2,
            },
            {
                "series": "CPIAUCSL",
                "period": "2025-01-01",
                "realtime_start": "2025-02-12",
                "realtime_end": "9999-12-31",
                "value": latest_value,
                "source_output_type": 2,
            },
        ]
    )


def _write_manifest(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _publish_upstream(
    root: Path,
    *,
    frame: pd.DataFrame | None = None,
    hardened: bool = True,
    collected_at: str = "2025-02-13T00:01:00Z",
    completed_at: str = "2025-02-13T00:02:00Z",
) -> tuple[Path, Path, dict]:
    upstream = root / "upstream"
    upstream.mkdir(parents=True, exist_ok=True)
    artifact_path = upstream / "CPIAUCSL_all_vintages.parquet"
    manifest_path = upstream / "manifest.json"
    matrix = (frame if frame is not None else _matrix()).copy()
    matrix.to_parquet(artifact_path, index=False)
    artifact_body = artifact_path.read_bytes()
    periods = pd.to_datetime(matrix["period"])
    releases = pd.to_datetime(matrix["realtime_start"])
    row = {
        "status": "written",
        # A runner-absolute path is untrusted metadata. The explicit input path wins.
        "path": "/hostile/runner/path/CPIAUCSL_all_vintages.parquet",
        "rows": len(matrix),
        "periods": int(periods.nunique()),
        "release_dates": int(releases.nunique()),
        "period_min": periods.min().date().isoformat(),
        "period_max": periods.max().date().isoformat(),
    }
    manifest: dict = {
        "schema": "release_target_vintage_collection.v1",
        "status": "ok",
        "source": "FRED/ALFRED",
        "source_output_type": 2,
        "realtime_start": "1997-01-01",
        "collected_at": collected_at,
        "dry_run": False,
        "series": {"CPIAUCSL": row},
    }
    if hardened:
        manifest.update(
            {
                "integrity_profile": sources.COLLECTOR_INTEGRITY_PROFILE,
                "completed_at": completed_at,
            }
        )
        row.update(
            {
                "artifact_sha256": hashlib.sha256(artifact_body).hexdigest(),
                "artifact_bytes": len(artifact_body),
            }
        )
    _write_manifest(manifest_path, manifest)
    return manifest_path, artifact_path, manifest


def _intake(
    root: Path,
    *,
    hardened: bool = True,
) -> sources.StoredSourceArtifact:
    manifest_path, artifact_path, _manifest = _publish_upstream(root, hardened=hardened)
    return sources.intake_alfred_cpiaucsl(
        root / "private-source-store",
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )


def test_hardened_intake_binds_exact_bytes_and_reader_returns_stable_projection(
    tmp_path: Path,
) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(tmp_path)
    upstream_body = artifact_path.read_bytes()

    stored = sources.intake_alfred_cpiaucsl(
        tmp_path / "private-source-store",
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    receipt = stored.receipt
    reader = sources.SourceArtifactReader(tmp_path / "private-source-store")

    assert stored.created is True
    assert stored.artifact == {
        "schema": sources.SOURCE_SCHEMA,
        "source_id": sources.SOURCE_ID,
        "series_id": "CPIAUCSL",
        "source_output_type": 2,
        "vintage_date": "2025-02-12",
        "measurement_start": "2024-12-01",
        "measurement_end_exclusive": "2025-02-01",
        "rows": [
            {
                "period": "2024-12-01",
                "realtime_start": "2025-02-12",
                "realtime_end": "9999-12-31",
                "value": 110.0,
            },
            {
                "period": "2025-01-01",
                "realtime_start": "2025-02-12",
                "realtime_end": "9999-12-31",
                "value": 111.1,
            },
        ],
    }
    assert receipt["provenance"]["evidence_basis"] == "live_captured_source_vintage"
    assert (
        receipt["provenance"]["upstream_artifact_sha256"]
        == hashlib.sha256(upstream_body).hexdigest()
    )
    assert receipt["provenance"]["upstream_artifact_bytes"] == len(upstream_body)
    assert (
        receipt["provenance"]["manifest_sha256"]
        == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    )
    assert receipt["provenance"]["manifest_bytes"] == len(manifest_path.read_bytes())
    assert receipt["quality"] == {
        "status": "complete",
        "reconstruction_only": False,
        "source_evidence_eligible": True,
        "feature_projection_eligible": False,
        "training_eligible": False,
        "promotion_eligible": False,
    }
    assert receipt["authority"] == dict(market_memory.AUTHORITY)
    assert reader.pinned_generation_id is None
    assert reader.head_generation_id() == stored.generation_id
    assert reader.pinned_generation_id is None
    assert reader.read_receipt(receipt["receipt_id"]) == receipt
    assert reader.pinned_generation_id == stored.generation_id
    assert reader.read_object(receipt["receipt_id"]) == stored.artifact


def test_canonical_sealed_manifest_replays_existing_capture_without_rewriting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(
        tmp_path, hardened=False
    )
    store = tmp_path / "private-source-store"
    first = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    first_manifest_sha = first.receipt["provenance"]["manifest_sha256"]
    assert first.receipt["provenance"]["evidence_basis"] == "public_reconstruction"
    assert first.receipt["quality"]["source_evidence_eligible"] is False
    inventory_before = {
        path.relative_to(store).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in store.rglob("*")
        if path.is_file()
    }

    artifact_body = artifact_path.read_bytes()
    manifest["integrity_profile"] = sources.COLLECTOR_INTEGRITY_PROFILE
    manifest["completed_at"] = "2025-02-13T00:02:00Z"
    manifest["mode"] = "seal_existing"
    manifest["sealed_at"] = "2025-02-13T00:02:30Z"
    manifest["series"]["CPIAUCSL"].update(
        {
            "status": "sealed",
            "artifact_sha256": hashlib.sha256(artifact_body).hexdigest(),
            "artifact_bytes": len(artifact_body),
        }
    )
    _write_manifest(manifest_path, manifest)
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() != first_manifest_sha

    _set_source_clock(monkeypatch, "2025-02-13T00:05:00Z")
    replay = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )

    assert replay.created is False
    assert replay.generation_id == first.generation_id
    assert replay.receipt == first.receipt
    assert replay.receipt["provenance"]["evidence_basis"] == "public_reconstruction"
    assert replay.receipt["quality"]["source_evidence_eligible"] is False
    assert sources.SourceArtifactReader(store).receipts() == [first.receipt]
    assert {
        path.relative_to(store).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in store.rglob("*")
        if path.is_file()
    } == inventory_before


def test_sealed_manifest_cannot_mint_first_live_evidence_receipt(
    tmp_path: Path,
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    manifest["mode"] = "seal_existing"
    manifest["sealed_at"] = "2025-02-13T00:02:30Z"
    manifest["series"]["CPIAUCSL"]["status"] = "sealed"
    _write_manifest(manifest_path, manifest)
    store = tmp_path / "private-source-store"

    with pytest.raises(
        sources.SourceIntakeError, match="no unique published matching revision"
    ):
        sources.intake_alfred_cpiaucsl(
            store,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    assert not store.exists()


def test_sealed_manifest_cannot_adopt_a_different_unpublished_revision(
    tmp_path: Path,
) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(
        tmp_path, hardened=False
    )
    store = tmp_path / "private-source-store"
    sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    inventory_before = {
        path.relative_to(store).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in store.rglob("*")
        if path.is_file()
    }

    manifest_path, artifact_path, manifest = _publish_upstream(
        tmp_path, frame=_matrix(latest_value=112.2)
    )
    manifest["mode"] = "seal_existing"
    manifest["sealed_at"] = "2025-02-13T00:02:30Z"
    manifest["series"]["CPIAUCSL"]["status"] = "sealed"
    _write_manifest(manifest_path, manifest)

    with pytest.raises(
        sources.SourceIntakeError, match="no unique published matching revision"
    ):
        sources.intake_alfred_cpiaucsl(
            store,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    assert {
        path.relative_to(store).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
        )
        for path in store.rglob("*")
        if path.is_file()
    } == inventory_before


def test_sealed_manifest_cannot_downgrade_when_all_hardening_fields_are_absent(
    tmp_path: Path,
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    manifest["mode"] = "seal_existing"
    manifest["sealed_at"] = "2025-02-13T00:02:30Z"
    manifest["series"]["CPIAUCSL"]["status"] = "sealed"
    del manifest["integrity_profile"]
    del manifest["completed_at"]
    del manifest["series"]["CPIAUCSL"]["artifact_sha256"]
    del manifest["series"]["CPIAUCSL"]["artifact_bytes"]
    _write_manifest(manifest_path, manifest)

    with pytest.raises(sources.SourceIntakeError, match="complete hardened profile"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


@pytest.mark.parametrize(
    ("mode", "sealed_at", "message"),
    [
        (None, "2025-02-13T00:02:30Z", "canonical mode"),
        ("seal_existing", None, "sealed_at"),
        ("seal_existing", "2025-02-13T00:01:30Z", "clocks are impossible"),
        ("seal_existing", "2025-02-13T00:04:00Z", "clocks are impossible"),
    ],
)
def test_sealed_manifest_requires_canonical_mode_and_clock_envelope(
    tmp_path: Path,
    mode: str | None,
    sealed_at: str | None,
    message: str,
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    manifest["series"]["CPIAUCSL"]["status"] = "sealed"
    if mode is not None:
        manifest["mode"] = mode
    if sealed_at is not None:
        manifest["sealed_at"] = sealed_at
    _write_manifest(manifest_path, manifest)

    with pytest.raises(sources.SourceIntakeError, match=message):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


@pytest.mark.parametrize(
    ("manifest_status", "row_status", "mode", "sealed_at", "message"),
    [
        (
            "partial",
            "sealed",
            "seal_existing",
            "2025-02-13T00:02:30Z",
            "not complete",
        ),
        (
            "ok",
            "written",
            "seal_existing",
            "2025-02-13T00:02:30Z",
            "claims sealed provenance",
        ),
        (
            "ok",
            "written",
            None,
            "2025-02-13T00:02:30Z",
            "claims sealed provenance",
        ),
    ],
)
def test_collector_seal_markers_cannot_be_downgraded_or_partially_published(
    tmp_path: Path,
    manifest_status: str,
    row_status: str,
    mode: str | None,
    sealed_at: str,
    message: str,
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    manifest["status"] = manifest_status
    manifest["series"]["CPIAUCSL"]["status"] = row_status
    if mode is not None:
        manifest["mode"] = mode
    manifest["sealed_at"] = sealed_at
    _write_manifest(manifest_path, manifest)

    with pytest.raises(sources.SourceIntakeError, match=message):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


def test_source_receipt_json_schema_accepts_both_evidence_classes_and_rejects_drift(
    tmp_path: Path,
) -> None:
    schema_path = (
        ROOT / "contracts/market_memory/source_artifact_receipt.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    hardened = _intake(tmp_path / "hardened").receipt
    legacy = _intake(tmp_path / "legacy", hardened=False).receipt

    validator.validate(hardened)
    validator.validate(legacy)

    mutants = []
    authority_drift = copy.deepcopy(hardened)
    authority_drift["authority"]["may_rank"] = True
    mutants.append(authority_drift)
    extra_field = copy.deepcopy(hardened)
    extra_field["future_contract_field"] = True
    mutants.append(extra_field)
    feature_promotion = copy.deepcopy(hardened)
    feature_promotion["quality"]["feature_projection_eligible"] = True
    mutants.append(feature_promotion)
    trust_class_drift = copy.deepcopy(hardened)
    trust_class_drift["provenance"]["evidence_basis"] = "public_reconstruction"
    mutants.append(trust_class_drift)

    for mutant in mutants:
        with pytest.raises(ValidationError):
            validator.validate(mutant)


def test_legacy_v1_is_reconstruction_only_and_hardened_attestation_appends(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path, hardened=False)
    store = tmp_path / "private-source-store"

    legacy = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )

    assert legacy.receipt["provenance"]["evidence_basis"] == "public_reconstruction"
    assert legacy.receipt["provenance"]["integrity_profile"] == (
        "legacy_unbound_manifest.v1"
    )
    assert legacy.receipt["clocks"]["collector_completed_at"] is None
    assert legacy.receipt["quality"] == {
        "status": "complete",
        "reconstruction_only": True,
        "source_evidence_eligible": False,
        "feature_projection_eligible": False,
        "training_eligible": False,
        "promotion_eligible": False,
    }

    # A later hardened attestation is new evidence: append it without rewriting
    # or silently promoting the previously preserved reconstruction receipt.
    artifact_body = artifact_path.read_bytes()
    manifest["integrity_profile"] = sources.COLLECTOR_INTEGRITY_PROFILE
    manifest["completed_at"] = "2025-02-13T00:04:00Z"
    manifest["series"]["CPIAUCSL"].update(
        {
            "artifact_sha256": hashlib.sha256(artifact_body).hexdigest(),
            "artifact_bytes": len(artifact_body),
        }
    )
    _write_manifest(manifest_path, manifest)
    _set_source_clock(monkeypatch, "2025-02-13T00:05:00Z")
    retry = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )

    assert retry.created is True
    assert retry.generation_id != legacy.generation_id
    assert retry.receipt["capture_id"] != legacy.receipt["capture_id"]
    assert retry.receipt["receipt_id"] != legacy.receipt["receipt_id"]
    assert retry.receipt["vintage_id"] == legacy.receipt["vintage_id"]
    assert retry.receipt["revision_id"] == legacy.receipt["revision_id"]
    assert retry.receipt["quality"]["reconstruction_only"] is False
    assert retry.receipt["quality"]["source_evidence_eligible"] is True
    receipts = sources.SourceArtifactReader(store).receipts()
    assert {row["receipt_id"] for row in receipts} == {
        legacy.receipt["receipt_id"],
        retry.receipt["receipt_id"],
    }
    preserved = next(
        row for row in receipts if row["receipt_id"] == legacy.receipt["receipt_id"]
    )
    assert preserved["quality"]["reconstruction_only"] is True
    assert sources.SourceArtifactReader(store, legacy.generation_id).receipts() == [
        legacy.receipt
    ]


@pytest.mark.parametrize(
    "missing_field",
    ["integrity_profile", "completed_at", "artifact_sha256", "artifact_bytes"],
)
def test_partial_hardening_never_falls_back_to_reconstruction(
    tmp_path: Path, missing_field: str
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    if missing_field in {"artifact_sha256", "artifact_bytes"}:
        del manifest["series"]["CPIAUCSL"][missing_field]
    else:
        del manifest[missing_field]
    _write_manifest(manifest_path, manifest)

    with pytest.raises(sources.SourceIntakeError):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


def test_all_null_hardening_keys_reject_instead_of_downgrading(
    tmp_path: Path,
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    manifest["integrity_profile"] = None
    manifest["completed_at"] = None
    manifest["series"]["CPIAUCSL"]["artifact_sha256"] = None
    manifest["series"]["CPIAUCSL"]["artifact_bytes"] = None
    _write_manifest(manifest_path, manifest)

    with pytest.raises(sources.SourceIntakeError):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


def test_manifest_boolean_counts_and_impossible_realtime_intervals_fail_closed(
    tmp_path: Path,
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path / "counts")
    manifest["series"]["CPIAUCSL"]["rows"] = True
    _write_manifest(manifest_path, manifest)
    with pytest.raises(sources.SourceIntakeError, match="positive integer"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "count-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    impossible = _matrix()
    impossible.loc[1, "realtime_end"] = "2025-02-11"
    manifest_path, artifact_path, _manifest = _publish_upstream(
        tmp_path / "interval", frame=impossible
    )
    with pytest.raises(sources.SourceIntakeError, match="ends before it starts"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "interval-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


def test_date_precision_uses_conservative_upper_bound_and_preserves_observation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(
        tmp_path,
        collected_at="2025-02-12T23:00:00Z",
        completed_at="2025-02-12T23:30:00Z",
    )

    _set_source_clock(monkeypatch, "2025-02-12T23:59:59Z")
    with pytest.raises(sources.SourceIntakeError, match="conservative availability"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "too-early",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    _set_source_clock(monkeypatch, "2025-02-13T00:00:00Z")
    stored = sources.intake_alfred_cpiaucsl(
        tmp_path / "at-upper-bound",
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    assert stored.receipt["clocks"] == {
        "source_date": "2025-02-12",
        "availability_lower_bound": "2025-02-12T00:00:00Z",
        "availability_upper_bound": "2025-02-13T00:00:00Z",
        "available_at": "2025-02-13T00:00:00Z",
        "observed_at": "2025-02-13T00:00:00Z",
        "collector_started_at": "2025-02-12T23:00:00Z",
        "collector_completed_at": "2025-02-12T23:30:00Z",
    }
    assert stored.receipt["availability_evidence"] == {
        "precision": "date",
        "timestamp_inferred": False,
        "rule": "source_date_upper_bound.v1",
        "operational_cutoff_uses": "observed_at",
    }


def test_historical_capture_keeps_late_observation_instead_of_backdating_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(
        tmp_path,
        collected_at="2026-08-10T12:00:00Z",
        completed_at="2026-08-10T12:01:00Z",
    )

    _set_source_clock(monkeypatch, "2026-08-10T12:02:00Z")
    stored = sources.intake_alfred_cpiaucsl(
        tmp_path / "private-source-store",
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )

    assert stored.receipt["clocks"]["available_at"] == "2025-02-13T00:00:00Z"
    assert stored.receipt["clocks"]["collector_completed_at"] == "2026-08-10T12:01:00Z"
    assert stored.receipt["clocks"]["observed_at"] == "2026-08-10T12:02:00Z"
    assert (
        stored.receipt["clocks"]["observed_at"]
        != stored.receipt["clocks"]["available_at"]
    )


def test_completion_and_observation_clock_ordering_fail_closed(tmp_path: Path) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(
        tmp_path,
        collected_at="2025-02-13T00:02:00Z",
        completed_at="2025-02-13T00:01:00Z",
    )
    with pytest.raises(sources.SourceIntakeError, match="clocks are impossible"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "bad-completion",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    manifest_path, artifact_path, _manifest = _publish_upstream(
        tmp_path / "second",
        completed_at="2025-02-13T00:04:00Z",
    )
    with pytest.raises(sources.SourceIntakeError, match="clocks are impossible"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "bad-observation",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


def test_identical_intake_is_idempotent_across_later_observation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(tmp_path)
    store = tmp_path / "private-source-store"
    first = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    _set_source_clock(monkeypatch, "2025-02-13T00:10:00Z")
    second = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )

    assert second.created is False
    assert second == sources.StoredSourceArtifact(
        first.artifact, first.receipt, first.generation_id, False
    )
    assert len(list(store.glob("source_objects/*/*.json"))) == 1
    assert len(list(store.glob("source_receipts/*/*.json"))) == 1
    assert len(list(store.glob("source_captures/*/*.json"))) == 1
    assert len(list(store.glob("source_generations/*/*.json"))) == 2


def test_changed_bytes_same_vintage_append_and_pinned_generation_stays_stable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    store = tmp_path / "private-source-store"
    first = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    pinned = sources.SourceArtifactReader(store)
    assert pinned.receipts() == [first.receipt]
    assert pinned.pinned_generation_id == first.generation_id

    _matrix(latest_value=111.2).to_parquet(artifact_path, index=False)
    artifact_body = artifact_path.read_bytes()
    manifest["completed_at"] = "2025-02-13T00:04:00Z"
    manifest["series"]["CPIAUCSL"].update(
        {
            "artifact_sha256": hashlib.sha256(artifact_body).hexdigest(),
            "artifact_bytes": len(artifact_body),
        }
    )
    _write_manifest(manifest_path, manifest)
    _set_source_clock(monkeypatch, "2025-02-13T00:05:00Z")
    second = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )

    assert second.created is True
    assert second.generation_id != first.generation_id
    assert second.receipt["vintage_id"] == first.receipt["vintage_id"]
    assert second.receipt["revision_id"] != first.receipt["revision_id"]
    assert second.receipt["artifact_sha256"] != first.receipt["artifact_sha256"]
    assert pinned.head_generation_id() == second.generation_id
    assert pinned.pinned_generation_id == first.generation_id
    assert pinned.receipts() == [first.receipt]
    with pytest.raises(sources.SourceNotFound):
        pinned.read_receipt(second.receipt["receipt_id"])
    current = sources.SourceArtifactReader(store)
    assert {row["receipt_id"] for row in current.receipts()} == {
        first.receipt["receipt_id"],
        second.receipt["receipt_id"],
    }
    assert current.read_object(first.receipt["receipt_id"]) == first.artifact


def test_manifest_race_is_detected_across_artifact_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, manifest = _publish_upstream(tmp_path)
    original = sources._read_bounded
    manifest_reads = 0

    def racing_read(path: Path, *, limit: int, label: str):
        nonlocal manifest_reads
        result = original(path, limit=limit, label=label)
        if label == "collector manifest":
            manifest_reads += 1
            if manifest_reads == 1:
                changed = copy.deepcopy(manifest)
                changed["race_marker"] = True
                _write_manifest(manifest_path, changed)
        return result

    monkeypatch.setattr(sources, "_read_bounded", racing_read)
    with pytest.raises(sources.SourceIntakeError, match="changed during stable intake"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


def test_default_observation_clock_is_stamped_after_stable_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(tmp_path)
    events: list[str] = []
    original = sources._read_bounded

    def recording_read(path: Path, *, limit: int, label: str):
        events.append(label)
        return original(path, limit=limit, label=label)

    def clock() -> datetime:
        events.append("observed_at")
        return datetime(2025, 2, 13, 0, 3, tzinfo=timezone.utc)

    monkeypatch.setattr(sources, "_read_bounded", recording_read)
    monkeypatch.setattr(sources, "_utc_now", clock)
    sources.intake_alfred_cpiaucsl(
        tmp_path / "private-source-store",
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )

    assert events == [
        "collector manifest",
        "CPIAUCSL artifact",
        "collector manifest",
        "observed_at",
    ]


def test_corrupt_oversize_and_partial_inputs_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    corrupt_root = tmp_path / "corrupt"
    manifest_path, artifact_path, manifest = _publish_upstream(corrupt_root)
    artifact_path.write_bytes(b"not a parquet artifact")
    artifact_body = artifact_path.read_bytes()
    manifest["series"]["CPIAUCSL"].update(
        {
            "artifact_sha256": hashlib.sha256(artifact_body).hexdigest(),
            "artifact_bytes": len(artifact_body),
        }
    )
    _write_manifest(manifest_path, manifest)
    with pytest.raises(sources.SourceIntakeError, match="valid full-vintage matrix"):
        sources.intake_alfred_cpiaucsl(
            corrupt_root / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    duplicate_root = tmp_path / "duplicate-json"
    manifest_path, artifact_path, _manifest = _publish_upstream(duplicate_root)
    manifest_path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(sources.SourceIntakeError, match="strict JSON"):
        sources.intake_alfred_cpiaucsl(
            duplicate_root / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    oversize_root = tmp_path / "oversize"
    manifest_path, artifact_path, _manifest = _publish_upstream(oversize_root)
    monkeypatch.setattr(sources, "_MAX_MANIFEST_BYTES", 32)
    with pytest.raises(sources.SourceIntakeError, match="safe size bound"):
        sources.intake_alfred_cpiaucsl(
            oversize_root / "private-source-store",
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )


def test_store_without_complete_head_is_unavailable_not_a_proven_absence(
    tmp_path: Path,
) -> None:
    store = tmp_path / "private-source-store"
    with pytest.raises(sources.SourceStoreError, match="manifest"):
        sources.SourceArtifactReader(store).receipts()

    stored = _intake(tmp_path)
    (store / "SOURCE_HEAD.json").unlink()
    with pytest.raises(sources.SourceStoreError, match="HEAD"):
        sources.SourceArtifactReader(store).read_receipt(stored.receipt["receipt_id"])


def test_crash_before_head_keeps_orphans_invisible_and_retry_recovers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(tmp_path)
    store = tmp_path / "private-source-store"
    original_replace = sources._replace_head
    calls = 0

    def fail_second_head(root: Path, head: dict) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sources.SourceStoreError("injected source HEAD crash")
        original_replace(root, head)

    monkeypatch.setattr(sources, "_replace_head", fail_second_head)
    with pytest.raises(sources.SourceStoreError, match="HEAD crash"):
        sources.intake_alfred_cpiaucsl(
            store,
            manifest_path=manifest_path,
            artifact_path=artifact_path,
        )

    orphan = json.loads(
        next(store.glob("source_captures/*/*.json")).read_text(encoding="utf-8")
    )
    reader = sources.SourceArtifactReader(store)
    assert reader.receipts() == []
    with pytest.raises(sources.SourceNotFound):
        reader.read_receipt(orphan["receipt_id"])

    monkeypatch.setattr(sources, "_replace_head", original_replace)
    _set_source_clock(monkeypatch, "2025-02-13T00:10:00Z")
    recovered = sources.intake_alfred_cpiaucsl(
        store,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
    )
    assert recovered.created is True
    assert sources.SourceArtifactReader(store).receipts() == [recovered.receipt]


@pytest.mark.parametrize("target", ["object", "receipt", "generation", "head"])
def test_tampered_store_layers_fail_closed(tmp_path: Path, target: str) -> None:
    case_root = tmp_path / target
    stored = _intake(case_root)
    store = case_root / "private-source-store"

    if target == "object":
        path = store / stored.receipt["object_key"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["rows"][0]["value"] += 1
    elif target == "receipt":
        path = next(store.glob("source_receipts/*/*.json"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["quality"]["training_eligible"] = True
    elif target == "generation":
        path = next(store.glob(f"source_generations/*/{stored.generation_id}.json"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["previous_generation_id"] = None
    else:
        path = store / "SOURCE_HEAD.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["generation_sha256"] = "0" * 64
    path.write_bytes(sources._canonical_bytes(payload))

    reader = sources.SourceArtifactReader(store)
    with pytest.raises(sources.SourceStoreError):
        if target == "object":
            reader.read_object(stored.receipt["receipt_id"])
        else:
            reader.read_receipt(stored.receipt["receipt_id"])


def test_source_state_is_not_exposed_to_api_or_public_site(tmp_path: Path) -> None:
    del tmp_path  # Boundary is source/static inspection; no runtime store is mounted.
    route_paths = {route.path for route in market_memory_api.router.routes}
    api_source = (ROOT / "app/market_memory.py").read_text(encoding="utf-8")
    api_unit = (ROOT / "app/deploy/macro-api.service").read_text(encoding="utf-8")

    assert not any("source" in path for path in route_paths)
    assert "market_memory_sources" not in api_source
    assert "InaccessiblePaths=/var/lib/macro-market-memory/state" in api_unit
    assert "InaccessiblePaths=-/var/lib/macro-market-memory/state" not in api_unit
    assert not list((ROOT / "site").glob("**/source_receipts"))
    assert not list((ROOT / "site.served").glob("**/source_receipts"))


def test_source_store_root_rejects_broad_repository_and_public_targets() -> None:
    for unsafe in (Path("/"), Path.home(), ROOT, ROOT / "site" / "market-memory"):
        with pytest.raises(sources.SourceStoreError):
            sources.validate_source_store_root(unsafe)


def test_w1b_source_paths_and_suites_share_the_market_memory_ci_gate() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = (ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
    lane = jobs.split("  market-memory-contract:", 1)[1].split("\n  group-pulse:", 1)[0]

    for path in (
        "engine/neuralweb/market_memory_sources.py",
        "contracts/market_memory/source_artifact_receipt.v1.schema.json",
        "scripts/collect_release_target_vintages.py",
        "scripts/ingest_market_memory_sources.py",
        "app/deploy/macro-market-memory-source.service",
        "app/deploy/macro-market-memory-source.timer",
        "tests/test_market_memory_sources.py",
        "tests/test_market_memory_source_deploy.py",
        "tests/test_release_target_truth.py",
    ):
        assert f'      - "{path}"' in workflow
    assert "pip install pytest fastapi httpx numpy pandas pyarrow" in lane
    assert "tests/test_market_memory_sources.py" in lane
    assert "tests/test_market_memory_source_deploy.py" in lane
    assert "tests/test_release_target_truth.py" in lane


def test_source_receipt_has_no_feature_options_outcome_or_prophet_authority(
    tmp_path: Path,
) -> None:
    stored = _intake(tmp_path)
    receipt = stored.receipt

    assert receipt["authority"] == dict(market_memory.AUTHORITY)
    assert receipt["authority"]["context_only"] is True
    assert receipt["authority"]["proposal_weight"] == 0
    assert receipt["authority"]["may_rank"] is False
    assert receipt["authority"]["may_gate"] is False
    assert receipt["authority"]["may_size"] is False
    assert receipt["authority"]["may_trade"] is False
    assert receipt["authority"]["may_select_options_candidate"] is False
    assert receipt["authority"]["may_write_options_episode"] is False
    assert receipt["authority"]["may_append_outcome"] is False
    assert receipt["authority"]["may_train_prophet"] is False
    assert not {
        "feature_receipts",
        "options",
        "signal_episode",
        "outcome",
        "label",
        "prophet",
    }.intersection(receipt)


def test_intake_rejects_symlink_inputs_before_resolving_them(tmp_path: Path) -> None:
    manifest_path, artifact_path, _manifest = _publish_upstream(tmp_path / "real")
    alias = tmp_path / "alias"
    alias.mkdir()
    manifest_alias = alias / "manifest.json"
    artifact_alias = alias / "CPIAUCSL_all_vintages.parquet"
    manifest_alias.symlink_to(manifest_path)
    artifact_alias.symlink_to(artifact_path)

    with pytest.raises(sources.SourceIntakeError, match="opened safely"):
        sources.intake_alfred_cpiaucsl(
            tmp_path / "private-source-store",
            manifest_path=manifest_alias,
            artifact_path=artifact_alias,
        )
