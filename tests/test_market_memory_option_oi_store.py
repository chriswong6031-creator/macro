"""Hostile tests for the private W1B.5 option-OI availability store."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pickle
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine.neuralweb import market_memory_option_oi_observation as observation
from engine.neuralweb import market_memory_option_oi_store as store

ROOT = Path(__file__).resolve().parents[1]
STORE_SCHEMA_PATH = ROOT / "contracts/market_memory/option_oi_store.v1.schema.json"
CAPTURE_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/option_oi_capture_receipt.v1.schema.json"
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _git_blob_oid(body: bytes) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    return hashlib.sha1(framed).hexdigest()


def _bundle(
    *,
    available_at: str = "2026-08-10T18:00:00.000000Z",
    pinned_commit: str = "1" * 40,
    open_interest: int = 17,
) -> observation.OptionOiObservationBundle:
    response_body = _canonical(
        {
            "results": [
                {
                    "details": {"ticker": "O:SPY260821C00500000"},
                    "open_interest": open_interest,
                },
                {
                    "details": {"ticker": "O:SPY260821P00500000"},
                    "open_interest": None,
                },
                {"details": {"ticker": "O:SPY260821C00510000"}},
            ],
            "status": "OK",
        }
    )
    config_body = (ROOT / "config/market_memory_option_oi_source.v1.json").read_bytes()
    license_body = (
        ROOT / "research/licenses/MASSIVE_ENTITLEMENT_RECORD.md"
    ).read_bytes()
    return observation.project_current_spy_option_oi_observation(
        observation.PinnedOptionOiInputs(
            fetched_response=observation.FetchedOptionOiResponse(
                status=200,
                url=observation.SOURCE_URL,
                selected_headers=(
                    ("content-type", "application/json"),
                    ("content-length", str(len(response_body))),
                ),
                body=response_body,
                response_body_completed_at=available_at,
            ),
            pinned_sources=observation.PinnedOptionOiSources(
                pinned_commit=pinned_commit,
                source_config_body=config_body,
                license_record_body=license_body,
                git_blob_oids=(
                    ("option_oi_source_config", _git_blob_oid(config_body)),
                    ("massive_entitlement_record", _git_blob_oid(license_body)),
                ),
            ),
        )
    )


def _root(tmp_path: Path) -> Path:
    return tmp_path.resolve() / "options-v1"


def _capture(
    tmp_path: Path,
    *,
    bundle: observation.OptionOiObservationBundle | None = None,
) -> tuple[Path, store.StoredOptionOiObservation]:
    root = _root(tmp_path)
    stored = store.capture_option_oi_observation(
        root,
        bundle=_bundle() if bundle is None else bundle,
    )
    return root, stored


def _object_path(root: Path, object_key: str) -> Path:
    return root.joinpath(*object_key.split("/"))


def _write_canonical(path: Path, value: object) -> None:
    path.write_bytes(_canonical(value))


def test_store_and_capture_schemas_are_meta_valid_and_accept_real_objects(
    tmp_path: Path,
) -> None:
    store_schema = json.loads(STORE_SCHEMA_PATH.read_text())
    capture_schema = json.loads(CAPTURE_SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(store_schema)
    Draft202012Validator.check_schema(capture_schema)

    root, stored = _capture(tmp_path)
    manifest = json.loads((root / "store_manifest.json").read_text())
    Draft202012Validator(store_schema).validate(manifest)
    Draft202012Validator(capture_schema).validate(stored.capture_receipt)


def test_initialize_creates_one_complete_empty_private_generation(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    first = store.initialize_option_oi_store(root)
    second = store.initialize_option_oi_store(root)
    assert first == second
    assert first["capture_count"] == 0
    assert first["schema"] == store.STORE_SCHEMA
    assert stat_mode(root) == 0o700
    assert stat_mode(root / "store_manifest.json") == 0o600
    generation = store.load_option_oi_generation(root)
    assert generation["captures"] == []


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_capture_round_trips_all_five_exact_bodies_and_private_receipts(
    tmp_path: Path,
) -> None:
    candidate = _bundle()
    root, stored = _capture(tmp_path, bundle=candidate)
    assert stored.bundle.probe_receipt_bytes == candidate.probe_receipt_bytes
    assert stored.bundle.source_observation_bytes == candidate.source_observation_bytes
    assert (
        stored.bundle.pinned_inputs.fetched_response.body
        == candidate.pinned_inputs.fetched_response.body
    )
    assert (
        stored.bundle.pinned_inputs.pinned_sources.source_config_body
        == candidate.pinned_inputs.pinned_sources.source_config_body
    )
    assert (
        stored.bundle.pinned_inputs.pinned_sources.license_record_body
        == candidate.pinned_inputs.pinned_sources.license_record_body
    )
    receipt = stored.capture_receipt
    for ref in receipt["source_bodies"].values():
        assert stat_mode(_object_path(root, ref["object_key"])) == 0o600
    assert (
        stat_mode(_object_path(root, receipt["source_observation"]["object_key"]))
        == 0o600
    )
    assert (
        stat_mode(_object_path(root, receipt["probe_receipt"]["object_key"])) == 0o600
    )


def test_receipt_exposes_only_source_availability_not_option_values(
    tmp_path: Path,
) -> None:
    root, stored = _capture(tmp_path)
    projected = _canonical(stored.capture_receipt) + _canonical(
        store.load_option_oi_generation(root)
    )
    for forbidden in (
        b"O:SPY",
        b'open_interest":17',
        b"gex_value",
        b"expiration_date",
        b"strike_price",
    ):
        assert forbidden not in projected
    assert stored.capture_receipt["completeness"] == {
        "page_complete": True,
        "continuation_followed": False,
        "intentionally_bounded": True,
        "chain_complete": False,
        "contract_universe_complete": False,
        "atomic_chain_snapshot_verified": False,
    }
    policy = stored.capture_receipt["evidence_policy"]
    assert policy["raw_entity_body_preserved_in_private_cas"] is True
    assert policy["raw_entity_body_publicly_exposed"] is False
    assert policy["vendor_tickers_projected"] is False
    assert policy["open_interest_values_projected"] is False
    assert policy["source_payload_contract_validated"] is True
    assert policy["exact_source_bodies_integrity_bound"] is True
    assert policy["provider_response_signed"] is False
    assert policy["raw_cas_durable_before_prepared_clock"] is True
    assert policy["prepared_self_recoverable_from_cas"] is True
    assert policy["prepared_temporaries_isolated_from_scan"] is True
    assert "contract_validated" not in policy
    assert "exact_source_bodies_authenticated" not in policy


def test_availability_clock_is_exact_response_completion_without_calendar_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = "2026-08-10T03:04:05.000000Z"
    observed = "2026-08-10T03:04:06.000000Z"
    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: datetime_from_utc(observed),
    )
    _, stored = _capture(tmp_path, bundle=_bundle(available_at=clock))
    assert stored.capture_receipt["clocks"] == {
        "available_at": clock,
        "first_observed_at": observed,
        "response_body_completed_at": clock,
    }
    source = stored.bundle.source_observation
    assert source["temporal"]["event_time"] is None
    assert source["temporal"]["measurement_time"] is None
    assert source["temporal"]["calendar_used"] is False
    assert "session" not in stored.capture_receipt
    assert "date" not in stored.capture_receipt
    assert (
        store.load_option_oi_generation(_root(tmp_path))["captures"][0][
            "first_observed_at"
        ]
        == observed
    )


def datetime_from_utc(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_identical_retry_is_idempotent_and_does_not_advance_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _bundle()
    root, first = _capture(tmp_path, bundle=candidate)
    head_path = root / "HEAD.json"
    before = (head_path.read_bytes(), head_path.stat().st_mtime_ns)
    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("idempotent retry resampled")),
    )
    second = store.capture_option_oi_observation(root, bundle=candidate)
    after = (head_path.read_bytes(), head_path.stat().st_mtime_ns)
    assert second.capture_receipt == first.capture_receipt
    assert second.generation_id == first.generation_id
    assert before == after
    assert len(store.load_option_oi_generation(root)["captures"]) == 1


def test_store_clock_must_not_precede_response_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    available = "2026-08-10T18:00:00.000000Z"
    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: datetime_from_utc("2026-08-10T17:59:59.999999Z"),
    )
    root = _root(tmp_path)
    with pytest.raises(
        store.MarketMemoryOptionOiCaptureError,
        match="predates response-body completion",
    ):
        store.capture_option_oi_observation(
            root,
            bundle=_bundle(available_at=available),
        )
    assert store.load_option_oi_generation(root)["captures"] == []
    assert not (root / "prepared").exists()


def test_complete_recovery_cas_is_durable_before_store_clock_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    sampled = False

    def assert_cas_then_sample():
        nonlocal sampled
        assert len(list((root / "source_bodies").glob("*/*.bin"))) == 3
        assert len(list((root / "source_observations").glob("*/*.json"))) == 1
        assert len(list((root / "probe_receipts").glob("*/*.json"))) == 1
        assert not (root / "prepared").exists()
        sampled = True
        return datetime_from_utc("2026-08-10T18:00:01.000000Z")

    monkeypatch.setattr(store, "_utc_now", assert_cas_then_sample)
    store.capture_option_oi_observation(root, bundle=_bundle())
    assert sampled is True


def test_same_response_at_a_later_completion_clock_is_a_new_observation(
    tmp_path: Path,
) -> None:
    root, first = _capture(tmp_path, bundle=_bundle())
    second = store.capture_option_oi_observation(
        root,
        bundle=_bundle(available_at="2026-08-10T18:01:00.000000Z"),
    )
    generation = store.load_option_oi_generation(root)
    assert first.capture_receipt["capture_id"] != second.capture_receipt["capture_id"]
    assert len(generation["captures"]) == 2
    assert [row["available_at"] for row in generation["captures"]] == sorted(
        row["available_at"] for row in generation["captures"]
    )


def test_same_exact_sources_from_a_new_code_commit_remain_idempotent(
    tmp_path: Path,
) -> None:
    root, first = _capture(tmp_path, bundle=_bundle(pinned_commit="1" * 40))
    second = store.capture_option_oi_observation(
        root,
        bundle=_bundle(pinned_commit="2" * 40),
    )
    assert second.capture_receipt == first.capture_receipt
    assert len(store.load_option_oi_generation(root)["captures"]) == 1


def test_invalid_bundle_is_rejected_before_any_filesystem_mutation(
    tmp_path: Path,
) -> None:
    candidate = _bundle()
    tampered = copy.deepcopy(candidate.source_observation)
    tampered["available_at"] = "2026-08-10T18:01:00.000000Z"
    invalid = replace(candidate, source_observation=tampered)
    root = _root(tmp_path)
    with pytest.raises(store.MarketMemoryOptionOiCaptureError):
        store.capture_option_oi_observation(root, bundle=invalid)
    assert not root.exists()


@pytest.mark.parametrize(
    "relative",
    ["options", "trusted-v1", "public/options-v1", "site/options-v1"],
)
def test_store_root_rejects_wrong_or_public_profiles(
    tmp_path: Path, relative: str
) -> None:
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.validate_option_oi_store_root(tmp_path.resolve() / relative)


def test_store_root_rejects_repository_descendants(tmp_path: Path) -> None:
    repository = tmp_path.resolve() / "repo"
    repository.mkdir(mode=0o700)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.validate_option_oi_store_root(
            repository / "private" / "options-v1",
            repository_root=repository,
        )


def test_store_root_rejects_old_market_memory_tree() -> None:
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.validate_option_oi_store_root(
            "/var/lib/macro-market-memory/state/options-v1"
        )


def test_store_root_rejects_broad_or_wrong_new_canonical_tree() -> None:
    for path in (
        "/var/lib/macro-market-memory-options",
        "/var/lib/macro-market-memory-options/state/options-v1",
        "/var/lib/macro-market-memory-options/other/options-v1",
    ):
        with pytest.raises(store.MarketMemoryOptionOiStoreError):
            store.validate_option_oi_store_root(path)


def test_store_root_rejects_symlink_parent_and_root(tmp_path: Path) -> None:
    real = tmp_path.resolve() / "real"
    real.mkdir(mode=0o700)
    link = tmp_path.resolve() / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.validate_option_oi_store_root(link / "options-v1")
    real_root = real / "options-v1"
    real_root.mkdir(mode=0o700)
    root_link = tmp_path.resolve() / "options-v1"
    root_link.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.validate_option_oi_store_root(root_link)


def test_store_root_rejects_group_or_world_permissions(tmp_path: Path) -> None:
    root = _root(tmp_path)
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.initialize_option_oi_store(root)


def test_default_root_uses_separate_production_tree_and_exact_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MARKET_MEMORY_OPTION_OI_STORE_DIR", raising=False)
    original_validator = store.validate_option_oi_store_root
    monkeypatch.setattr(
        store,
        "validate_option_oi_store_root",
        lambda candidate, **_kwargs: Path(candidate),
    )
    assert store.default_option_oi_store_root("/opt/macro") == Path(
        "/var/lib/macro-market-memory-options/options-v1"
    )
    monkeypatch.setattr(store, "validate_option_oi_store_root", original_validator)
    override = tmp_path.resolve() / "override" / "options-v1"
    monkeypatch.setenv("MARKET_MEMORY_OPTION_OI_STORE_DIR", str(override))
    assert store.default_option_oi_store_root(ROOT) == override


@pytest.mark.parametrize(
    "role",
    [
        "option_oi_response_body",
        "option_oi_source_config",
        "massive_entitlement_record",
    ],
)
def test_tampered_source_cas_is_rejected(tmp_path: Path, role: str) -> None:
    root, stored = _capture(tmp_path)
    ref = stored.capture_receipt["source_bodies"][role]
    path = _object_path(root, ref["object_key"])
    body = path.read_bytes()
    path.write_bytes(body[:-1] + bytes([body[-1] ^ 1]))
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.load_option_oi_capture(
            root,
            capture_id=stored.capture_receipt["capture_id"],
        )


@pytest.mark.parametrize("object_name", ["source_observation", "probe_receipt"])
def test_tampered_projected_object_is_rejected(
    tmp_path: Path, object_name: str
) -> None:
    root, stored = _capture(tmp_path)
    ref = stored.capture_receipt[object_name]
    path = _object_path(root, ref["object_key"])
    payload = json.loads(path.read_text())
    payload["profile"] = "tampered"
    _write_canonical(path, payload)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.load_option_oi_capture(
            root,
            capture_id=stored.capture_receipt["capture_id"],
        )


def test_tampered_capture_receipt_is_rejected(tmp_path: Path) -> None:
    root, stored = _capture(tmp_path)
    path = root / stored.capture_receipt["prepared_object_key"]
    assert path.exists()
    receipt_path = (
        root
        / "capture_receipts"
        / stored.capture_receipt["capture_id"][-64:-62]
        / f"{stored.capture_receipt['capture_id']}.json"
    )
    receipt = json.loads(receipt_path.read_text())
    receipt["completeness"]["chain_complete"] = True
    _write_canonical(receipt_path, receipt)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.load_option_oi_capture(
            root,
            capture_id=stored.capture_receipt["capture_id"],
        )


def test_tampered_prepared_record_is_rejected(tmp_path: Path) -> None:
    root, stored = _capture(tmp_path)
    path = root / stored.capture_receipt["prepared_object_key"]
    prepared = json.loads(path.read_text())
    prepared["authority"]["may_trade"] = True
    _write_canonical(path, prepared)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.load_option_oi_capture(
            root,
            capture_id=stored.capture_receipt["capture_id"],
        )


def test_tampered_head_or_generation_is_rejected(tmp_path: Path) -> None:
    root, _ = _capture(tmp_path)
    head_path = root / "HEAD.json"
    head = json.loads(head_path.read_text())
    head["generation_sha256"] = "0" * 64
    _write_canonical(head_path, head)
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.load_option_oi_generation(root)


def test_noncanonical_generation_json_is_rejected(tmp_path: Path) -> None:
    root, _ = _capture(tmp_path)
    head = json.loads((root / "HEAD.json").read_text())
    generation_path = (
        root
        / "generations"
        / head["generation_id"][-64:-62]
        / f"{head['generation_id']}.json"
    )
    generation_path.write_bytes(generation_path.read_bytes() + b"\n")
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.load_option_oi_generation(root)


def test_pinned_generation_cannot_see_a_later_capture(tmp_path: Path) -> None:
    root, first = _capture(tmp_path)
    first_generation = first.generation_id
    second = store.capture_option_oi_observation(
        root,
        bundle=_bundle(available_at="2026-08-10T18:01:00.000000Z"),
    )
    loaded_first = store.load_option_oi_capture(
        root,
        capture_id=first.capture_receipt["capture_id"],
        generation_id=first_generation,
    )
    assert loaded_first.capture_receipt == first.capture_receipt
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.load_option_oi_capture(
            root,
            capture_id=second.capture_receipt["capture_id"],
            generation_id=first_generation,
        )


def test_crash_after_prepared_reuses_exact_completion_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    candidate = _bundle()
    observed = "2026-08-10T18:00:01.000000Z"
    monkeypatch.setattr(store, "_utc_now", lambda: datetime_from_utc(observed))
    original = store._publish_prepared_capture
    monkeypatch.setattr(
        store,
        "_publish_prepared_capture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            store.MarketMemoryOptionOiStoreError("simulated crash")
        ),
    )
    with pytest.raises(store.MarketMemoryOptionOiStoreError, match="simulated crash"):
        store.capture_option_oi_observation(root, bundle=candidate)
    prepared_paths = list((root / "prepared").glob("*/*.json"))
    assert len(prepared_paths) == 1
    prepared_before = prepared_paths[0].read_bytes()
    assert json.loads(prepared_before)["first_observed_at"] == observed
    assert len(list((root / "source_bodies").glob("*/*.bin"))) == 3
    assert len(list((root / "source_observations").glob("*/*.json"))) == 1
    assert len(list((root / "probe_receipts").glob("*/*.json"))) == 1
    assert store.load_option_oi_generation(root)["captures"] == []

    monkeypatch.setattr(store, "_publish_prepared_capture", original)
    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("prepared retry resampled")),
    )
    monkeypatch.setattr(
        observation,
        "fetch_current_spy_option_oi_response",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("resume attempted a network fetch")
        ),
    )
    resumed = store.resume_pending_option_oi_captures(root)
    assert len(resumed) == 1
    stored = resumed[0]
    assert prepared_paths[0].read_bytes() == prepared_before
    assert stored.capture_receipt["clocks"]["available_at"] == (
        candidate.pinned_inputs.fetched_response.response_body_completed_at
    )
    assert stored.capture_receipt["clocks"]["first_observed_at"] == observed
    assert store.resume_pending_option_oi_captures(root) == ()


def test_failure_before_prepared_leaves_no_observation_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    monkeypatch.setattr(
        store,
        "_write_prepared_create_once",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            store.MarketMemoryOptionOiStoreError("pre-prepared crash")
        ),
    )
    with pytest.raises(store.MarketMemoryOptionOiStoreError, match="pre-prepared"):
        store.capture_option_oi_observation(root, bundle=_bundle())
    assert not (root / "prepared").exists()
    assert len(list((root / "source_bodies").glob("*/*.bin"))) == 3
    assert len(list((root / "source_observations").glob("*/*.json"))) == 1
    assert len(list((root / "probe_receipts").glob("*/*.json"))) == 1
    assert store.load_option_oi_generation(root)["captures"] == []
    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("empty resume sampled clock")),
    )
    assert store.resume_pending_option_oi_captures(root) == ()


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process crash")
def test_process_exit_after_durable_prepared_link_leaves_resumable_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    candidate = _bundle()
    candidate_path = tmp_path / "candidate.pickle"
    candidate_path.write_bytes(pickle.dumps(candidate))
    child_code = """
import os
import pickle
from pathlib import Path

from engine.neuralweb import market_memory_option_oi_store as store

root = Path(os.environ["OPTION_OI_CRASH_ROOT"])
candidate = pickle.loads(Path(os.environ["OPTION_OI_CRASH_BUNDLE"]).read_bytes())
prepared_tree = root / "prepared"
original_directory_fsync = store.market_memory_pit._directory_fsync

def exit_after_prepared_fsync(path):
    original_directory_fsync(path)
    if Path(path).parent == prepared_tree:
        os._exit(92)

store.market_memory_pit._directory_fsync = exit_after_prepared_fsync
try:
    store.capture_option_oi_observation(root, bundle=candidate)
except BaseException:
    os._exit(93)
os._exit(94)
"""
    child_env = os.environ.copy()
    child_env["OPTION_OI_CRASH_ROOT"] = os.fspath(root)
    child_env["OPTION_OI_CRASH_BUNDLE"] = os.fspath(candidate_path)
    completed = subprocess.run(
        [sys.executable, "-c", child_code],
        cwd=ROOT,
        env=child_env,
        check=False,
    )
    assert completed.returncode == 92
    prepared_paths = list((root / "prepared").glob("*/*.json"))
    scratch_paths = list((root / "scratch" / "prepared").iterdir())
    assert len(prepared_paths) == 1
    assert len(scratch_paths) == 1
    assert scratch_paths[0].name.startswith(".mmoptionoiprepared_")
    prepared_before = prepared_paths[0].read_bytes()
    prepared = json.loads(prepared_before)

    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("resume sampled a clock")),
    )
    monkeypatch.setattr(
        observation,
        "fetch_current_spy_option_oi_response",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("resume attempted a network fetch")
        ),
    )
    resumed = store.resume_pending_option_oi_captures(root)
    assert len(resumed) == 1
    assert prepared_paths[0].read_bytes() == prepared_before
    clocks = resumed[0].capture_receipt["clocks"]
    assert clocks["available_at"] == prepared["available_at"]
    assert clocks["response_body_completed_at"] == prepared["available_at"]
    assert clocks["first_observed_at"] == prepared["first_observed_at"]
    assert list((root / "scratch" / "prepared").iterdir()) == []
    assert store.resume_pending_option_oi_captures(root) == ()


def test_pending_resume_fails_closed_on_tampered_recovery_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    original = store._publish_prepared_capture
    monkeypatch.setattr(
        store,
        "_publish_prepared_capture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            store.MarketMemoryOptionOiStoreError("leave pending")
        ),
    )
    with pytest.raises(store.MarketMemoryOptionOiStoreError, match="leave pending"):
        store.capture_option_oi_observation(root, bundle=_bundle())
    monkeypatch.setattr(store, "_publish_prepared_capture", original)
    prepared = json.loads(next((root / "prepared").glob("*/*.json")).read_text())
    response_ref = prepared["source_bodies"]["option_oi_response_body"]
    response_path = _object_path(root, response_ref["object_key"])
    body = response_path.read_bytes()
    response_path.write_bytes(body[:-1] + bytes([body[-1] ^ 1]))
    head_before = (root / "HEAD.json").read_bytes()
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.resume_pending_option_oi_captures(root)
    assert (root / "HEAD.json").read_bytes() == head_before
    assert store.load_option_oi_generation(root)["captures"] == []


def test_multiple_pending_records_resume_in_bounded_deterministic_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    observed_clocks = iter(
        (
            "2026-08-10T18:05:00.000000Z",
            "2026-08-10T18:04:00.000000Z",
        )
    )
    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: datetime_from_utc(next(observed_clocks)),
    )
    original = store._publish_prepared_capture
    monkeypatch.setattr(
        store,
        "_publish_prepared_capture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            store.MarketMemoryOptionOiStoreError("leave pending")
        ),
    )
    for available_at in (
        "2026-08-10T18:00:00.000000Z",
        "2026-08-10T18:01:00.000000Z",
    ):
        with pytest.raises(store.MarketMemoryOptionOiStoreError, match="leave pending"):
            store.capture_option_oi_observation(
                root,
                bundle=_bundle(available_at=available_at),
            )
    monkeypatch.setattr(store, "_publish_prepared_capture", original)
    monkeypatch.setattr(
        store,
        "_utc_now",
        lambda: (_ for _ in ()).throw(AssertionError("resume resampled clock")),
    )
    resumed = store.resume_pending_option_oi_captures(root)
    assert [
        item.capture_receipt["clocks"]["first_observed_at"] for item in resumed
    ] == [
        "2026-08-10T18:04:00.000000Z",
        "2026-08-10T18:05:00.000000Z",
    ]
    assert len(store.load_option_oi_generation(root)["captures"]) == 2


def test_pending_scan_rejects_partial_or_noncanonical_prepared_file(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    store.initialize_option_oi_store(root)
    prefix = root / "prepared" / "aa"
    prefix.mkdir(parents=True, mode=0o700)
    (prefix / ".partial.tmp").write_bytes(b"partial")
    with pytest.raises(store.MarketMemoryOptionOiStoreError, match="noncanonical"):
        store.resume_pending_option_oi_captures(root)


def test_prepared_scratch_rejects_unknown_entries_and_broad_parent_permissions(
    tmp_path: Path,
) -> None:
    root = _root(tmp_path)
    store.initialize_option_oi_store(root)
    scratch = root / "scratch" / "prepared"
    scratch.mkdir(parents=True, mode=0o700)
    scratch.parent.chmod(0o700)
    unknown = scratch / "unowned.tmp"
    unknown.write_bytes(b"do not remove")
    unknown.chmod(0o600)
    with pytest.raises(store.MarketMemoryOptionOiStoreError, match="noncanonical"):
        store.resume_pending_option_oi_captures(root)
    assert unknown.read_bytes() == b"do not remove"

    unknown.unlink()
    scratch.parent.chmod(0o770)
    try:
        with pytest.raises(store.MarketMemoryOptionOiStoreError, match="parent"):
            store.resume_pending_option_oi_captures(root)
    finally:
        scratch.parent.chmod(0o700)


def test_prepared_scratch_scan_is_strictly_bounded(tmp_path: Path) -> None:
    root = _root(tmp_path)
    store.initialize_option_oi_store(root)
    scratch = root / "scratch" / "prepared"
    scratch.mkdir(parents=True, mode=0o700)
    scratch.parent.chmod(0o700)
    for index in range(store._MAX_PREPARED_SCRATCH_FILES + 1):
        temporary = scratch / (
            f".mmoptionoiprepared_{index:064x}.json.tmp.1.{index:032x}"
        )
        temporary.write_bytes(b"pending")
        temporary.chmod(0o600)
    with pytest.raises(store.MarketMemoryOptionOiStoreError, match="exceeds"):
        store.resume_pending_option_oi_captures(root)
    assert len(list(scratch.iterdir())) == store._MAX_PREPARED_SCRATCH_FILES + 1


def test_head_advances_only_after_every_immutable_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    original = store._replace_head
    checked = False

    def inspect_before_head(root_arg: Path, head: dict[str, object]) -> None:
        nonlocal checked
        if list((root_arg / "capture_receipts").glob("*/*.json")):
            assert list((root_arg / "prepared").glob("*/*.json"))
            assert len(list((root_arg / "source_bodies").glob("*/*.bin"))) == 3
            assert len(list((root_arg / "source_observations").glob("*/*.json"))) == 1
            assert len(list((root_arg / "probe_receipts").glob("*/*.json"))) == 1
            generation_id = str(head["generation_id"])
            assert list((root_arg / "generations").glob(f"*/{generation_id}.json"))
            checked = True
        original(root_arg, head)

    monkeypatch.setattr(store, "_replace_head", inspect_before_head)
    store.capture_option_oi_observation(root, bundle=_bundle())
    assert checked is True


def test_partial_store_without_head_cannot_hide_capture_objects(tmp_path: Path) -> None:
    root, _ = _capture(tmp_path)
    (root / "HEAD.json").unlink()
    with pytest.raises(store.MarketMemoryOptionOiStoreError):
        store.initialize_option_oi_store(root)


def test_capture_schema_rejects_any_authority_or_completeness_upgrade(
    tmp_path: Path,
) -> None:
    _, stored = _capture(tmp_path)
    validator = Draft202012Validator(json.loads(CAPTURE_SCHEMA_PATH.read_text()))
    for path, value in (
        (("authority", "may_execute"), True),
        (("evidence_policy", "training_eligible"), True),
        (("evidence_policy", "open_interest_values_projected"), True),
        (("completeness", "chain_complete"), True),
        (("completeness", "intentionally_bounded"), False),
    ):
        candidate = copy.deepcopy(stored.capture_receipt)
        candidate[path[0]][path[1]] = value
        with pytest.raises(ValidationError):
            validator.validate(candidate)


def test_generation_bound_fails_closed_before_head_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    store.initialize_option_oi_store(root)
    head_before = (root / "HEAD.json").read_bytes()
    monkeypatch.setattr(store, "_MAX_GENERATION_CAPTURES", 0)
    with pytest.raises(store.MarketMemoryOptionOiCaptureError, match="capture bound"):
        store.capture_option_oi_observation(root, bundle=_bundle())
    assert (root / "HEAD.json").read_bytes() == head_before
    assert store.load_option_oi_generation(root)["captures"] == []
