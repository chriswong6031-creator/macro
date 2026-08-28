"""Hostile tests for the private W1B.3A breadth actual-output store."""

from __future__ import annotations

import copy
import functools
import hashlib
import io
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine.neuralweb import market_memory_actual_output_store as store
from engine.neuralweb import market_memory_breadth_observation as breadth

ROOT = Path(__file__).resolve().parents[1]
STORE_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/breadth_actual_output_store.v1.schema.json"
)
CAPTURE_SCHEMA_PATH = (
    ROOT
    / "contracts/market_memory/breadth_actual_output_capture_receipt.v1.schema.json"
)
_SOURCE_PATHS = {
    "breadth_actual_output": "data/breadth/breadth.parquet",
    "current_constituents": "data/breadth/constituents.parquet",
    "canary_identity_config": "config/market_memory_canary.v1.json",
    "xnys_calendar_module": "lib/nyse_calendar.py",
}
_FROZEN_FIXTURE_SESSION = "2026-08-07"
# Byte-pinned captures from ONE nightly commit (448cfacc0957) so numerator and
# denominator share an era; the nightly revises historical ledger rows, so a
# live read is not stable. Twin rationale in
# tests/test_market_memory_breadth_observation.py. Advance both together.
_FROZEN_FIXTURE_PATHS = {
    "breadth_actual_output": (
        "tests/fixtures/market_memory/breadth_through_2026-08-07.parquet"
    ),
    "current_constituents": (
        "tests/fixtures/market_memory/constituents_2026-08-07.parquet"
    ),
}


def _git_blob_oid(body: bytes) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    return hashlib.sha1(framed).hexdigest()


@functools.lru_cache(maxsize=1)
def _frozen_breadth_body() -> bytes:
    """Keep store clock tests independent of the nightly-revised ledger."""

    body = (ROOT / _FROZEN_FIXTURE_PATHS["breadth_actual_output"]).read_bytes()
    frame = pd.read_parquet(io.BytesIO(body), engine="pyarrow")
    assert frame.index[-1].date().isoformat() == _FROZEN_FIXTURE_SESSION
    return body


def _inputs(
    *, breadth_body: bytes | None = None, pinned_commit: str = "1" * 40
) -> breadth.PinnedBreadthInputs:
    bodies = {role: (ROOT / path).read_bytes() for role, path in _SOURCE_PATHS.items()}
    bodies["current_constituents"] = (
        ROOT / _FROZEN_FIXTURE_PATHS["current_constituents"]
    ).read_bytes()
    bodies["breadth_actual_output"] = (
        _frozen_breadth_body() if breadth_body is None else breadth_body
    )
    return breadth.PinnedBreadthInputs(
        pinned_commit=pinned_commit,
        breadth_body=bodies["breadth_actual_output"],
        constituents_body=bodies["current_constituents"],
        canary_config_body=bodies["canary_identity_config"],
        calendar_module_body=bodies["xnys_calendar_module"],
        git_blob_oids=tuple(
            (role, _git_blob_oid(body)) for role, body in bodies.items()
        ),
    )


def _bundle(
    *, breadth_body: bytes | None = None, pinned_commit: str = "1" * 40
) -> breadth.BreadthSnapshotBundle:
    return breadth.project_current_breadth_snapshot(
        _inputs(breadth_body=breadth_body, pinned_commit=pinned_commit)
    )


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, engine="pyarrow", index=True)
    return buffer.getvalue()


def _revised_same_session_bundle() -> breadth.BreadthSnapshotBundle:
    frame = pd.read_parquet(io.BytesIO(_inputs().breadth_body), engine="pyarrow")
    # Historical ad_line is excluded from the semantic feature but the exact
    # source-body change must still append a distinct same-session revision.
    frame.iloc[0, frame.columns.get_loc("ad_line")] += 1
    return _bundle(breadth_body=_parquet_bytes(frame))


def _clock(value: str):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    return lambda: parsed.astimezone(timezone.utc)


def _capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    observed_at: str = "2026-08-10T01:00:00Z",
    candidate: breadth.BreadthSnapshotBundle | None = None,
) -> tuple[Path, store.StoredBreadthActualOutput]:
    root = tmp_path / "breadth-v1"
    monkeypatch.setattr(store, "_utc_now", _clock(observed_at))
    stored = store.capture_breadth_actual_output(
        root, bundle=_bundle() if candidate is None else candidate
    )
    return root, stored


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_canonical(path: Path, value: object) -> None:
    path.write_bytes(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def test_store_capture_is_private_exact_context_only_and_schema_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    receipt = stored.capture_receipt
    manifest = _read_json(root / "store_manifest.json")
    store_schema = json.loads(STORE_SCHEMA_PATH.read_text(encoding="utf-8"))
    capture_schema = json.loads(CAPTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(store_schema)
    Draft202012Validator.check_schema(capture_schema)
    Draft202012Validator(store_schema).validate(manifest)
    Draft202012Validator(capture_schema).validate(receipt)

    assert manifest["profile"] == store.STORE_PROFILE
    assert receipt["actual_output_capture"] is True
    assert receipt["clocks"] == {
        "first_observed_at": "2026-08-10T01:00:00Z",
        "available_at": "2026-08-10T01:00:00Z",
    }
    assert receipt["freshness"] == {
        "policy": "xnys_prior_session_or_same_day_after_2200z.v1",
        "observed_utc_date": "2026-08-10",
        "prior_session": "2026-08-07",
        "same_day_session": "2026-08-10",
        "same_day_not_before": "2026-08-10T22:00:00Z",
        "accepted_session": "2026-08-07",
        "accepted_via": "prior_session",
    }
    for value in (manifest, receipt):
        assert value["authority"]["context_only"] is True
        assert value["authority"]["proposal_weight"] == 0
        assert all(
            value["authority"][field] is False
            for field in (
                "may_rank",
                "may_gate",
                "may_size",
                "may_escalate",
                "may_trade",
                "may_originate",
                "may_select_options_candidate",
                "may_execute",
                "may_write_options_episode",
                "may_append_outcome",
                "may_train_prophet",
            )
        )
        assert value["evidence_policy"]["training_eligible"] is False
        assert value["evidence_policy"]["promotion_eligible"] is False
    assert stored.bundle.feature_object["quality"]["actual_output_source"] is True
    assert stored.bundle.feature_object["quality"]["training_eligible"] is False
    assert stored.bundle.feature_object["quality"]["promotion_eligible"] is False

    prepared_paths = list((root / "prepared").glob("*/*.json"))
    raw_paths = list((root / "source_bodies").glob("*/*.bin"))
    assert len(prepared_paths) == 1
    assert len(raw_paths) == 4
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in prepared_paths)
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in raw_paths)
    assert root.stat().st_mode & 0o777 == 0o700


def test_schemas_and_runtime_reject_unknown_fields_authority_and_freshness_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    manifest = _read_json(root / "store_manifest.json")
    receipt = stored.capture_receipt
    store_validator = Draft202012Validator(
        json.loads(STORE_SCHEMA_PATH.read_text(encoding="utf-8"))
    )
    capture_validator = Draft202012Validator(
        json.loads(CAPTURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    )

    manifest_mutants = []
    extra_manifest = copy.deepcopy(manifest)
    extra_manifest["public"] = True
    manifest_mutants.append(extra_manifest)
    training_manifest = copy.deepcopy(manifest)
    training_manifest["evidence_policy"]["training_eligible"] = True
    manifest_mutants.append(training_manifest)
    authority_manifest = copy.deepcopy(manifest)
    authority_manifest["authority"]["may_gate"] = True
    manifest_mutants.append(authority_manifest)
    for mutant in manifest_mutants:
        with pytest.raises(ValidationError):
            store_validator.validate(mutant)

    receipt_mutants = []
    extra_receipt = copy.deepcopy(receipt)
    extra_receipt["label"] = "future-return"
    receipt_mutants.append(extra_receipt)
    capture_false = copy.deepcopy(receipt)
    capture_false["actual_output_capture"] = False
    receipt_mutants.append(capture_false)
    promoted = copy.deepcopy(receipt)
    promoted["authority"]["may_train_prophet"] = True
    receipt_mutants.append(promoted)
    source_extra = copy.deepcopy(receipt)
    source_extra["source_observation"]["snapshot_id"] = receipt["feature_object"][
        "snapshot_id"
    ]
    receipt_mutants.append(source_extra)
    for mutant in receipt_mutants:
        with pytest.raises(ValidationError):
            capture_validator.validate(mutant)
        with pytest.raises(store.MarketMemoryActualOutputStoreError):
            store._validate_receipt(mutant, store_id=receipt["store_id"])

    # JSON Schema bounds the receipt shape and values; the frozen XNYS
    # evaluator enforces the cross-field calendar relationship at runtime.
    stale_rule = copy.deepcopy(receipt)
    stale_rule["freshness"]["prior_session"] = "2026-08-06"
    capture_validator.validate(stale_rule)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="freshness receipt drift"
    ):
        store._validate_receipt(stale_rule, store_id=receipt["store_id"])


def test_root_guard_rejects_broad_public_wrong_profile_and_symlink_roots(
    tmp_path: Path,
) -> None:
    wrong = tmp_path / "actual-output"
    public = tmp_path / "public" / "breadth-v1"
    for candidate in (Path("/"), Path.home(), wrong, public):
        with pytest.raises(store.MarketMemoryActualOutputStoreError):
            store.validate_actual_output_store_root(candidate)

    target = tmp_path / "safe" / "breadth-v1"
    target.mkdir(parents=True)
    linked = tmp_path / "breadth-v1"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="cannot be symlinks"
    ):
        store.validate_actual_output_store_root(linked)

    dangling_root = tmp_path / "dangling-final" / "breadth-v1"
    dangling_root.parent.mkdir()
    dangling_root.symlink_to(tmp_path / "does-not-exist", target_is_directory=True)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="cannot be symlinks"
    ):
        store.validate_actual_output_store_root(dangling_root)

    real_parent = tmp_path / "real-parent"
    (real_parent / "breadth-v1").mkdir(parents=True, mode=0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="cannot be symlinks"
    ):
        store.validate_actual_output_store_root(linked_parent / "breadth-v1")

    dangling_parent = tmp_path / "dangling-parent"
    dangling_parent.symlink_to(tmp_path / "missing-parent", target_is_directory=True)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="cannot be symlinks"
    ):
        store.validate_actual_output_store_root(dangling_parent / "breadth-v1")

    with pytest.raises(store.MarketMemoryActualOutputStoreError):
        store.validate_actual_output_store_root(ROOT, repository_root=ROOT)

    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError,
        match="repository or its descendants",
    ):
        store.validate_actual_output_store_root(
            repository / "private" / "breadth-v1",
            repository_root=repository,
        )

    with pytest.raises(store.MarketMemoryActualOutputStoreError):
        store.validate_actual_output_store_root(
            "/var/lib/macro-market-memory/state/identity-v1/breadth-v1"
        )

    local_default = store.default_breadth_actual_output_store_root(ROOT)
    assert local_default.name == "breadth-v1"
    assert ROOT not in local_default.parents
    assert Path.home() / ".local" / "state" / "macro-market-memory" in (
        local_default.parents
    )

    exposed = tmp_path / "exposed" / "breadth-v1"
    exposed.mkdir(parents=True, mode=0o755)
    exposed.chmod(0o755)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="group or world"
    ):
        store.validate_actual_output_store_root(exposed)


def test_invalid_bundle_fails_before_root_creation_or_clock_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _bundle()
    invalid = replace(
        candidate,
        feature_object_bytes=candidate.feature_object_bytes + b"\n",
    )

    def forbidden_clock() -> datetime:
        raise AssertionError("clock sampled before detached validation")

    monkeypatch.setattr(store, "_utc_now", forbidden_clock)
    root = tmp_path / "breadth-v1"
    with pytest.raises(
        store.MarketMemoryActualOutputCaptureError, match="detached validation"
    ):
        store.capture_breadth_actual_output(root, bundle=invalid)
    assert not root.exists()


@pytest.mark.parametrize(
    ("observed_at", "accepted_via"),
    [
        ("2026-08-07T22:00:00Z", "same_day_after_2200z"),
        ("2026-08-08T01:00:00Z", "prior_session"),
        ("2026-08-09T23:59:59Z", "prior_session"),
        ("2026-08-10T00:00:00Z", "prior_session"),
    ],
)
def test_freshness_accepts_same_day_threshold_weekend_and_monday(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observed_at: str,
    accepted_via: str,
) -> None:
    _root, stored = _capture(
        tmp_path / observed_at.replace(":", "-"),
        monkeypatch,
        observed_at=observed_at,
    )
    assert stored.capture_receipt["freshness"]["accepted_via"] == accepted_via
    assert stored.capture_receipt["freshness"]["accepted_session"] == "2026-08-07"


def test_freshness_rejects_same_day_before_threshold_without_prepared_or_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "breadth-v1"
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-07T21:59:59Z"))
    with pytest.raises(
        store.MarketMemoryActualOutputCaptureError, match="freshness window"
    ):
        store.capture_breadth_actual_output(root, bundle=_bundle())
    assert not (root / "prepared").exists()
    assert not (root / "source_bodies").exists()
    assert store.load_breadth_actual_output_generation(root)["captures"] == []


def test_freshness_rejects_arbitrarily_old_tip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frame = pd.read_parquet(io.BytesIO(_inputs().breadth_body), engine="pyarrow")
    stale = frame.loc[:"2020-01-02"].copy()
    candidate = _bundle(breadth_body=_parquet_bytes(stale))
    root = tmp_path / "breadth-v1"
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T01:00:00Z"))
    with pytest.raises(
        store.MarketMemoryActualOutputCaptureError, match="freshness window"
    ):
        store.capture_breadth_actual_output(root, bundle=candidate)
    assert not (root / "prepared").exists()
    assert not (root / "source_bodies").exists()
    assert store.load_breadth_actual_output_generation(root)["captures"] == []


def test_prepared_is_first_capture_write_and_crash_retry_reuses_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "breadth-v1"
    candidate = _bundle()
    store.initialize_breadth_actual_output_store(root)
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T01:02:03Z"))
    original_write_json = store._write_json_create_once

    def fail_after_raw_cas(*args: object, **kwargs: object) -> bool:
        label = kwargs.get("label")
        if label != "breadth source observation":
            return original_write_json(*args, **kwargs)
        prepared = list((root / "prepared").glob("*/*.json"))
        assert len(prepared) == 1
        assert len(list((root / "source_bodies").glob("*/*.bin"))) == 4
        assert not (root / "source_observations").exists()
        assert not (root / "feature_objects").exists()
        assert not (root / "capture_receipts").exists()
        raise store.MarketMemoryActualOutputStoreError("injected raw CAS crash")

    monkeypatch.setattr(store, "_write_json_create_once", fail_after_raw_cas)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="injected raw CAS crash"
    ):
        store.capture_breadth_actual_output(root, bundle=candidate)
    prepared_path = next((root / "prepared").glob("*/*.json"))
    prepared_before = prepared_path.read_bytes()
    assert store.load_breadth_actual_output_generation(root)["captures"] == []

    retry_clock_reads = 0

    def later_retry_clock() -> datetime:
        nonlocal retry_clock_reads
        retry_clock_reads += 1
        return datetime(2026, 8, 12, 1, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(store, "_write_json_create_once", original_write_json)
    monkeypatch.setattr(store, "_utc_now", later_retry_clock)
    stored = store.capture_breadth_actual_output(root, bundle=candidate)
    assert retry_clock_reads == 0
    assert prepared_path.read_bytes() == prepared_before
    assert stored.capture_receipt["clocks"] == {
        "first_observed_at": "2026-08-10T01:02:03Z",
        "available_at": "2026-08-10T01:02:03Z",
    }


def test_generation_is_durable_before_head_and_retry_completes_same_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "breadth-v1"
    candidate = _bundle()
    empty = store.initialize_breadth_actual_output_store(root)
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T01:00:00Z"))
    original_replace_head = store._replace_head

    def fail_head(_root: Path, _head: object) -> None:
        assert list((root / "source_bodies").glob("*/*.bin"))
        assert list((root / "source_observations").glob("*/*.json"))
        assert list((root / "feature_objects").glob("*/*.json"))
        assert list((root / "capture_receipts").glob("*/*.json"))
        assert len(list((root / "generations").glob("*/*.json"))) == 2
        raise store.MarketMemoryActualOutputStoreError("injected HEAD crash")

    monkeypatch.setattr(store, "_replace_head", fail_head)
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="injected HEAD crash"
    ):
        store.capture_breadth_actual_output(root, bundle=candidate)
    assert (
        store.load_breadth_actual_output_generation(root)["generation_id"]
        == empty["generation_id"]
    )

    monkeypatch.setattr(store, "_replace_head", original_replace_head)
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T02:00:00Z"))
    stored = store.capture_breadth_actual_output(root, bundle=candidate)
    assert stored.generation_id != empty["generation_id"]
    assert len(store.load_breadth_actual_output_generation(root)["captures"]) == 1


def test_identical_bytes_are_idempotent_across_code_only_commit_when_still_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, first = _capture(tmp_path, monkeypatch)
    first_head = (root / "HEAD.json").read_bytes()
    candidate = _bundle(pinned_commit="2" * 40)

    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-10T02:00:00Z"))
    second = store.capture_breadth_actual_output(root, bundle=candidate)
    assert second.capture_receipt == first.capture_receipt
    assert second.generation_id == first.generation_id
    assert (root / "HEAD.json").read_bytes() == first_head
    assert len(list((root / "prepared").glob("*/*.json"))) == 1
    assert len(list((root / "capture_receipts").glob("*/*.json"))) == 1


def test_idempotent_recapture_rechecks_current_freshness_without_mutating_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, first = _capture(tmp_path, monkeypatch)
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(store, "_utc_now", _clock("2026-08-12T01:00:00Z"))
    with pytest.raises(
        store.MarketMemoryActualOutputCaptureError, match="freshness window"
    ):
        store.capture_breadth_actual_output(root, bundle=_bundle())
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert (root / "HEAD.json").read_bytes() == before["HEAD.json"]
    assert (
        store.load_breadth_actual_output_capture(
            root, capture_id=first.capture_receipt["capture_id"]
        ).capture_receipt
        == first.capture_receipt
    )


def test_same_session_changed_bytes_append_revision_and_pinned_generation_is_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "breadth-v1"
    clocks = iter(
        [
            datetime(2026, 8, 10, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 10, 1, 1, tzinfo=timezone.utc),
        ]
    )
    monkeypatch.setattr(store, "_utc_now", lambda: next(clocks))
    first = store.capture_breadth_actual_output(root, bundle=_bundle())
    first_generation_body = (
        root
        / "generations"
        / first.generation_id.removeprefix("mmactualgeneration_")[:2]
        / f"{first.generation_id}.json"
    ).read_bytes()
    second = store.capture_breadth_actual_output(
        root, bundle=_revised_same_session_bundle()
    )

    assert second.capture_receipt["session"] == first.capture_receipt["session"]
    assert second.capture_receipt["revision_id"] != first.capture_receipt["revision_id"]
    assert second.capture_receipt["capture_id"] != first.capture_receipt["capture_id"]
    active = store.load_breadth_actual_output_generation(root)
    pinned = store.load_breadth_actual_output_generation(
        root, generation_id=first.generation_id
    )
    assert len(active["captures"]) == 2
    assert len(pinned["captures"]) == 1
    assert (
        root
        / "generations"
        / first.generation_id.removeprefix("mmactualgeneration_")[:2]
        / f"{first.generation_id}.json"
    ).read_bytes() == first_generation_body
    assert (
        store.load_breadth_actual_output_capture(
            root,
            capture_id=first.capture_receipt["capture_id"],
            generation_id=first.generation_id,
        ).capture_receipt
        == first.capture_receipt
    )
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="absent or ambiguous"
    ):
        store.load_breadth_actual_output_capture(
            root,
            capture_id=second.capture_receipt["capture_id"],
            generation_id=first.generation_id,
        )


@pytest.mark.parametrize(
    "target",
    [
        "raw",
        "source",
        "feature",
        "prepared",
        "receipt",
        "generation",
        "head",
        "feature_symlink",
    ],
)
def test_every_stored_layer_tamper_or_symlink_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    root, stored = _capture(tmp_path / target, monkeypatch)
    receipt = stored.capture_receipt
    capture_id = receipt["capture_id"]
    if target == "raw":
        path = root / receipt["source_bodies"]["breadth_actual_output"]["object_key"]
        body = bytearray(path.read_bytes())
        body[-1] ^= 1
        path.write_bytes(body)
    elif target == "source":
        path = root / receipt["source_observation"]["object_key"]
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "feature":
        path = root / receipt["feature_object"]["object_key"]
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "prepared":
        path = root / receipt["prepared_object_key"]
        value = _read_json(path)
        value["available_at"] = "2026-08-10T01:00:01Z"
        _write_canonical(path, value)
    elif target == "receipt":
        path = next((root / "capture_receipts").glob("*/*.json"))
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "generation":
        path = next(
            path
            for path in (root / "generations").glob("*/*.json")
            if path.name == f"{stored.generation_id}.json"
        )
        value = _read_json(path)
        value["captures"][0]["receipt_sha256"] = "f" * 64
        _write_canonical(path, value)
    elif target == "head":
        path = root / "HEAD.json"
        value = _read_json(path)
        value["future"] = True
        _write_canonical(path, value)
    elif target == "feature_symlink":
        path = root / receipt["feature_object"]["object_key"]
        backup = tmp_path / target / "feature-backup.json"
        backup.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(backup)
    else:  # pragma: no cover - parametrization is closed
        raise AssertionError(target)

    with pytest.raises(store.MarketMemoryActualOutputStoreError):
        store.load_breadth_actual_output_capture(root, capture_id=capture_id)


def test_explicit_generation_path_identity_and_capture_bounds_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, stored = _capture(tmp_path, monkeypatch)
    generation = store.load_breadth_actual_output_generation(root)
    fake_id = "mmactualgeneration_" + "f" * 64
    fake_path = root / "generations" / "ff" / f"{fake_id}.json"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    _write_canonical(fake_path, generation)
    with pytest.raises(store.MarketMemoryActualOutputStoreError):
        store.load_breadth_actual_output_generation(root, generation_id=fake_id)

    receipt_path = next((root / "capture_receipts").glob("*/*.json"))
    receipt_path.write_bytes(b"{" + b" " * (store._MAX_RECEIPT_BYTES + 1) + b"}")
    with pytest.raises(
        store.MarketMemoryActualOutputStoreError, match="safe size bound"
    ):
        store.load_breadth_actual_output_capture(
            root, capture_id=stored.capture_receipt["capture_id"]
        )
