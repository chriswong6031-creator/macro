"""Adversarial tests for the temp-only W2A forward-contract ledger."""

from __future__ import annotations

import ast
import json
import stat
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_forward as forward
from engine.neuralweb import market_memory_forward_store as store
from tests import market_memory_repo_scan as repo_scan
from tests.test_market_memory_forward import _synthetic_w1_packet

ROOT = Path(__file__).resolve().parents[1]
REGISTERED = "2026-08-01T12:00:00.000000Z"
SEALED = "2026-08-07T20:05:30.000000Z"
AVAILABLE = "2026-08-09T20:06:00.000000Z"
KNOWN = "2026-08-09T20:07:00.000000Z"
OBSERVED = "2026-08-09T20:08:00.000000Z"
RECORDED = "2026-08-09T20:09:00.000000Z"
OBSERVED_NOW = "2026-08-09T20:10:00.000000Z"
CORRECTION_OBSERVED_NOW = "2026-08-09T21:10:00.000000Z"


def _canonical(value: object) -> bytes:
    return forward.canonical_json_bytes(value)


def _rehash(value: dict[str, object], *, field: str, prefix: str) -> None:
    value[field] = ""
    value[field] = prefix + sha256(_canonical(value)).hexdigest()


def _context_bytes() -> bytes:
    return _canonical(_synthetic_w1_packet())


def _domain_states(context_bytes: bytes) -> list[dict[str, object]]:
    return forward._project_w1_domain_states(json.loads(context_bytes))


def _state(
    context_bytes: bytes, *, generation_sha256: str = "3" * 64
) -> dict[str, object]:
    return forward.build_state_snapshot(
        exact_context_bytes=context_bytes,
        store_id="mmstore_" + "1" * 64,
        generation_id="mmgeneration_" + "2" * 64,
        generation_sha256=generation_sha256,
        domain_states=_domain_states(context_bytes),
    )


def _trial(
    *,
    trial_key: str = "synthetic.spy.close.v1",
    baseline_config: str = "4" * 64,
    outcome_mark: str = "close",
    live_forward_start: str = "2026-08-02T00:00:00.000000Z",
) -> dict[str, object]:
    return forward.build_trial_registration(
        trial_key=trial_key,
        registered_at=REGISTERED,
        state_requirements={
            "state_schema": forward.STATE_SNAPSHOT_SCHEMA,
            "context_schema": mm.AS_KNOWN_AT_SCHEMA,
            "minimum_observed_domains": 2,
            "required_observed_domains": list(forward.CANONICAL_DOMAINS[:2]),
        },
        target={
            "target_id": "spy.close.return",
            "formula": "outcome_close / input_close - 1",
            "formula_version": "synthetic.v1",
            "value_type": "number",
            "unit": "ratio",
            "categories": [],
        },
        marks={
            "input_mark": "close",
            "outcome_mark": outcome_mark,
            "cost_convention": "none",
            "benchmark": "zero_return",
        },
        horizon={
            "anchor": "decision_cutoff",
            "start_offset_seconds": 86_400,
            "end_offset_seconds": 172_800,
            "evaluation_offset_seconds": 172_800,
        },
        distribution={"kind": "scalar", "quantile_levels": [], "categories": []},
        proper_score={"name": "squared_error", "orientation": "lower_is_better"},
        baselines=[
            {
                "baseline_id": "zero_return",
                "baseline_version": "synthetic.v1",
                "config_sha256": baseline_config,
            }
        ],
        splits={
            "development_start": "2020-01-01T00:00:00.000000Z",
            "development_end": "2022-01-01T00:00:00.000000Z",
            "test_start": "2022-01-01T00:00:00.000000Z",
            "test_end": "2024-01-01T00:00:00.000000Z",
            "live_forward_start": live_forward_start,
        },
        purge={"enabled": True, "before_seconds": 172_800, "after_seconds": 0},
        embargo={"enabled": True, "duration_seconds": 172_800},
        dependence={
            "keys": ["context_id"],
            "clustering": "exact_key_tuple",
            "cluster_version": "synthetic.v1",
        },
        trial_budget={
            "max_trials": 10,
            "max_variants": 2,
            "family_trials_already_registered": 0,
        },
        abstention={
            "required": True,
            "minimum_observed_domains": 2,
            "allowed_reasons": [
                "insufficient_domains",
                "policy_expired",
                "required_domain_missing",
            ],
        },
        expiry={"expires_at": "2027-01-01T00:00:00.000000Z", "action": "abstain"},
        demotion={"enabled": True, "triggers": ["broken_lineage"]},
        implementation={
            "model_sha256": "5" * 64,
            "code_sha256": "6" * 64,
            "config_sha256": "7" * 64,
        },
    )


def _forecast(
    *,
    context_bytes: bytes,
    state_record: dict[str, object],
    trial_record: dict[str, object],
    point: float = 0.02,
) -> dict[str, object]:
    return forward.build_forecast_record(
        trial_registration=trial_record,
        state_snapshot=state_record,
        exact_context_bytes=context_bytes,
        sealed_at=SEALED,
        disposition="issued",
        abstention_reason=None,
        model_sha256="5" * 64,
        code_sha256="6" * 64,
        config_sha256="7" * 64,
        predictive_distribution={
            "kind": "scalar",
            "point": point,
            "quantiles": [],
            "probabilities": [],
        },
    )


def _outcome(
    forecast_record: dict[str, object],
    *,
    value: float = 0.015,
    revision_number: int = 1,
    revision_of: str | None = None,
) -> dict[str, object]:
    correction = revision_number > 1
    return forward.build_outcome_record(
        outcome_event_id=forecast_record["outcome_event_id"],
        context_id=forecast_record["context_id"],
        target_sha256=forecast_record["target_sha256"],
        outcome_definition_sha256=forecast_record["outcome_definition_sha256"],
        horizon_start=forecast_record["horizon_start"],
        horizon_end=forecast_record["horizon_end"],
        evaluation_at=forecast_record["evaluation_at"],
        status="complete",
        outcome_value={"value_type": "number", "value": value, "unit": "ratio"},
        reason=None,
        effective_at=forecast_record["evaluation_at"],
        source_available_at=(
            "2026-08-09T21:06:00.000000Z" if correction else AVAILABLE
        ),
        known_at="2026-08-09T21:07:00.000000Z" if correction else KNOWN,
        observed_at="2026-08-09T21:08:00.000000Z" if correction else OBSERVED,
        recorded_at="2026-08-09T21:09:00.000000Z" if correction else RECORDED,
        source_receipts=[
            {
                "receipt_id": "synthetic.outcome.source.v1",
                "artifact_sha256": "8" * 64,
                "source_schema": "synthetic.price.v1",
                "source_version": "synthetic.v1",
            }
        ],
        revision_number=revision_number,
        revision_of=revision_of,
        revision_reason="source_revision" if revision_number > 1 else None,
    )


def _records() -> tuple[
    bytes,
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    trial_record = _trial()
    forecast_record = _forecast(
        context_bytes=context_bytes,
        state_record=state_record,
        trial_record=trial_record,
    )
    outcome_record = _outcome(forecast_record)
    return (
        context_bytes,
        state_record,
        trial_record,
        forecast_record,
        outcome_record,
    )


def _seed_through_forecast(
    root: Path,
) -> tuple[
    bytes,
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    records = _records()
    context_bytes, state_record, trial_record, forecast_record, _outcome_record = (
        records
    )
    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    store.append_trial(root, trial_record)
    store.append_forecast(root, forecast_record, exact_context_bytes=context_bytes)
    return records


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _kind_tree(root: Path, kind: str) -> dict[str, bytes]:
    base = root / "objects" / kind
    return {
        path.relative_to(base).as_posix(): path.read_bytes()
        for path in base.rglob("*")
        if path.is_file()
    }


def _head(root: Path) -> dict[str, object]:
    return json.loads((root / "HEAD.json").read_text(encoding="utf-8"))


def _initialized_root(tmp_path: Path) -> Path:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_path.chmod(0o700)
    root = tmp_path / "forward-v1"
    store.initialize_forward_store(root)
    return root


def test_initialization_is_explicit_temp_private_and_frozen(tmp_path: Path) -> None:
    root = tmp_path / "forward-v1"
    assert not root.exists()
    manifest = store.initialize_forward_store(root)

    assert manifest["policy"] == {
        "authority": "none",
        "emission_enabled": False,
        "live_inputs_allowed": False,
        "private": True,
        "promotion_eligible": False,
        "public_serving_allowed": False,
        "research_only": True,
        "synthetic_only": True,
        "training_eligible": False,
    }
    assert manifest["record_kinds"] == ["state", "trial", "forecast", "outcome"]
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
        for path in root.rglob("*")
    )
    assert _head(root)["record_count"] == 0


def test_root_rejects_relative_non_temp_symlink_and_public_mode(
    tmp_path: Path,
) -> None:
    with pytest.raises(store.MarketMemoryForwardStoreError, match="absolute"):
        store.initialize_forward_store(Path("forward-v1"))
    with pytest.raises(store.MarketMemoryForwardStoreError, match="temporary"):
        store.initialize_forward_store(ROOT / ".forward-v1")

    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="symlink"):
        store.initialize_forward_store(alias / "forward-v1")

    root = _initialized_root(tmp_path / "private-mode")
    root.chmod(0o750)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="private"):
        store.initialize_forward_store(root)


def test_store_module_has_no_default_root_env_cli_service_api_or_data_path() -> None:
    source = (ROOT / "engine/neuralweb/market_memory_forward_store.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    forbidden_literals = {
        "/var/lib",
        "MARKET_MEMORY",
        "argparse",
        "FastAPI",
        "APIRouter",
        "systemctl",
        "data/",
    }
    assert all(token not in source for token in forbidden_literals)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
        and node.func.attr in {"getenv", "environ"}
        for node in ast.walk(tree)
    )
    for function in (
        "initialize_forward_store",
        "append_state",
        "append_trial",
        "append_forecast",
        "append_outcome",
        "load_record",
        "load_generation",
        "replay_digest",
    ):
        definition = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        assert definition.args.args[0].arg == "root"
        assert definition.args.defaults == []


def test_no_production_python_imports_or_calls_the_temp_store() -> None:
    offenders: list[str] = []
    for path in repo_scan.production_python_paths():
        if path == ROOT / "engine/neuralweb/market_memory_forward_store.py":
            continue
        names = repo_scan.import_names(path)
        imported = (
            any(
                alias.endswith("market_memory_forward_store")
                for alias in names.imported
            )
            or any(
                module.endswith("market_memory_forward_store")
                for module in names.from_modules
            )
            or "market_memory_forward_store" in names.from_names
        )
        if imported:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_initial_generation_and_head_tamper_fail_closed(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    head = _head(root)
    generation_path = next((root / "generations").glob("*/*.json"))

    original = generation_path.read_bytes()
    generation_path.write_bytes(original + b"\n")
    generation_path.chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="canonical"):
        store.load_generation(root, head["generation_id"])
    generation_path.write_bytes(original)
    generation_path.chmod(0o600)

    head["record_count"] = 1
    (root / "HEAD.json").write_bytes(_canonical(head))
    (root / "HEAD.json").chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="count"):
        store.load_generation(root, head["generation_id"])


def test_symlinked_namespace_and_oversized_head_fail_closed(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    objects = root / "objects"
    moved = root / "objects-real"
    objects.rename(moved)
    objects.symlink_to(moved, target_is_directory=True)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="directory"):
        store.initialize_forward_store(root)

    objects.unlink()
    moved.rename(objects)
    (root / "HEAD.json").write_bytes(b"{" + b" " * (store._MAX_HEAD_BYTES + 1))
    (root / "HEAD.json").chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="size bound"):
        store.initialize_forward_store(root)


def test_manifest_lock_and_namespace_mode_tamper_fail_closed(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    manifest_path = root / "store_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["policy"]["emission_enabled"] = True
    manifest_path.write_bytes(_canonical(manifest))
    manifest_path.chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="policy"):
        store.initialize_forward_store(root)

    root = _initialized_root(tmp_path / "lock")
    (root / ".lock").write_bytes(b"substituted-lock\n")
    (root / ".lock").chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="lock identity"):
        store.initialize_forward_store(root)

    root = _initialized_root(tmp_path / "namespace")
    (root / "objects" / "state").chmod(0o750)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="private"):
        store.initialize_forward_store(root)


def test_replay_digest_is_nonce_independent_for_empty_stores(tmp_path: Path) -> None:
    first = _initialized_root(tmp_path / "a")
    second = _initialized_root(tmp_path / "b")
    first_head = _head(first)
    second_head = _head(second)

    assert first_head["generation_id"] != second_head["generation_id"]
    assert store.replay_digest(
        first, first_head["generation_id"]
    ) == store.replay_digest(second, second_head["generation_id"])
    assert (
        store.replay_digest(first, first_head["generation_id"])
        == sha256(_canonical([])).hexdigest()
    )


def test_four_kinds_append_load_and_replay_as_one_cumulative_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward-v1"
    context_bytes, state_record, trial_record, forecast_record, outcome_record = (
        _records()
    )

    state_result = store.append_state(
        root, state_record, exact_context_bytes=context_bytes
    )
    trial_result = store.append_trial(root, trial_record)
    forecast_result = store.append_forecast(
        root, forecast_record, exact_context_bytes=context_bytes
    )
    outcome_result = store.append_outcome(
        root, outcome_record, observed_now=OBSERVED_NOW
    )

    assert all(
        result.appended
        for result in (state_result, trial_result, forecast_result, outcome_result)
    )
    head = _head(root)
    assert head["record_count"] == 4
    assert head["counts"] == {
        kind: 1 for kind in ("state", "trial", "forecast", "outcome")
    }
    generation = store.load_generation(root, outcome_result.generation_id)
    assert [entry["kind"] for entry in generation["entries"]] == [
        "state",
        "trial",
        "forecast",
        "outcome",
    ]
    assert len(list((root / "generations").glob("*/*.json"))) == 5
    for kind, record in (
        ("state", state_record),
        ("trial", trial_record),
        ("forecast", forecast_record),
        ("outcome", outcome_record),
    ):
        record_id = record[store._ID_FIELD_BY_KIND[kind]]
        assert store.load_record(root, kind=kind, record_id=record_id) == record
        paths = list((root / "objects" / kind).glob("*/*.json"))
        assert len(paths) == 1
        assert paths[0].read_bytes() == _canonical(record)
    assert (
        store.replay_digest(root, outcome_result.generation_id) == head["replay_digest"]
    )


def test_identical_retries_are_byte_exact_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "forward-v1"
    context_bytes, state_record, trial_record, forecast_record, outcome_record = (
        _records()
    )
    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    store.append_trial(root, trial_record)
    store.append_forecast(root, forecast_record, exact_context_bytes=context_bytes)
    store.append_outcome(root, outcome_record, observed_now=OBSERVED_NOW)
    before = _tree(root)

    results = (
        store.append_state(root, state_record, exact_context_bytes=context_bytes),
        store.append_trial(root, trial_record),
        store.append_forecast(root, forecast_record, exact_context_bytes=context_bytes),
        store.append_outcome(root, outcome_record, observed_now=OBSERVED_NOW),
    )

    assert not any(result.appended for result in results)
    assert _tree(root) == before


def test_state_trial_and_forecast_semantic_keys_hard_conflict(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward-v1"
    context_bytes, state_record, trial_record, forecast_record, _outcome_record = (
        _records()
    )
    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    before_state_conflict = _tree(root)
    divergent_state = _state(context_bytes, generation_sha256="9" * 64)
    assert divergent_state["context_id"] == state_record["context_id"]
    assert divergent_state["state_snapshot_id"] != state_record["state_snapshot_id"]
    with pytest.raises(store.MarketMemoryForwardConflictError, match="semantic key"):
        store.append_state(root, divergent_state, exact_context_bytes=context_bytes)
    assert _tree(root) == before_state_conflict

    store.append_trial(root, trial_record)
    divergent_trial = _trial(baseline_config="9" * 64)
    assert divergent_trial["trial_key"] == trial_record["trial_key"]
    assert (
        divergent_trial["trial_registration_id"]
        != trial_record["trial_registration_id"]
    )
    before_trial_conflict = _tree(root)
    with pytest.raises(store.MarketMemoryForwardConflictError, match="semantic key"):
        store.append_trial(root, divergent_trial)
    assert _tree(root) == before_trial_conflict

    store.append_forecast(root, forecast_record, exact_context_bytes=context_bytes)
    divergent_forecast = _forecast(
        context_bytes=context_bytes,
        state_record=state_record,
        trial_record=trial_record,
        point=-0.03,
    )
    assert divergent_forecast["forecast_key"] == forecast_record["forecast_key"]
    assert divergent_forecast["forecast_id"] != forecast_record["forecast_id"]
    before_forecast_conflict = _tree(root)
    with pytest.raises(store.MarketMemoryForwardConflictError, match="semantic key"):
        store.append_forecast(
            root, divergent_forecast, exact_context_bytes=context_bytes
        )
    assert _tree(root) == before_forecast_conflict


def test_store_separates_outcome_events_with_different_frozen_marks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mark-bound-events"
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    close_trial = _trial()
    adjusted_trial = _trial(
        trial_key="synthetic.spy.adjusted_close.v1",
        outcome_mark="adjusted_close",
    )
    close_forecast = _forecast(
        context_bytes=context_bytes,
        state_record=state_record,
        trial_record=close_trial,
    )
    adjusted_forecast = _forecast(
        context_bytes=context_bytes,
        state_record=state_record,
        trial_record=adjusted_trial,
    )
    assert close_forecast["outcome_event_id"] != adjusted_forecast["outcome_event_id"]

    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    store.append_trial(root, close_trial)
    store.append_trial(root, adjusted_trial)
    store.append_forecast(root, close_forecast, exact_context_bytes=context_bytes)
    store.append_forecast(root, adjusted_forecast, exact_context_bytes=context_bytes)
    close_outcome = _outcome(close_forecast)
    result = store.append_outcome(root, close_outcome, observed_now=OBSERVED_NOW)
    assert result.appended


def test_dependencies_and_exact_context_are_required_before_any_append(
    tmp_path: Path,
) -> None:
    context_bytes, state_record, trial_record, forecast_record, outcome_record = (
        _records()
    )
    wrong_context = context_bytes + b" "
    root = tmp_path / "bad-context" / "forward-v1"
    with pytest.raises(store.MarketMemoryForwardConflictError, match="exact W1"):
        store.append_state(root, state_record, exact_context_bytes=wrong_context)
    assert not root.exists()

    root = _initialized_root(tmp_path / "missing-dependencies")
    before = _tree(root)
    with pytest.raises(
        store.MarketMemoryForwardConflictError, match="trial_registration"
    ):
        store.append_forecast(root, forecast_record, exact_context_bytes=context_bytes)
    assert _tree(root) == before
    with pytest.raises(store.MarketMemoryForwardConflictError, match="stored forecast"):
        store.append_outcome(root, outcome_record, observed_now=OBSERVED_NOW)
    assert _tree(root) == before

    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    store.append_trial(root, trial_record)
    before_wrong_join = _tree(root)
    with pytest.raises(store.MarketMemoryForwardConflictError, match="exact context"):
        store.append_forecast(root, forecast_record, exact_context_bytes=wrong_context)
    assert _tree(root) == before_wrong_join


def test_premature_outcome_rejects_without_touching_prior_kinds(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward-v1"
    _context, _state_record, _trial_record, _forecast_record, outcome_record = (
        _seed_through_forecast(root)
    )
    before = {kind: _kind_tree(root, kind) for kind in ("state", "trial", "forecast")}
    head_before = (root / "HEAD.json").read_bytes()

    with pytest.raises(store.MarketMemoryForwardMaturityError, match="recorded_at"):
        store.append_outcome(root, outcome_record, observed_now=OBSERVED)

    assert {kind: _kind_tree(root, kind) for kind in before} == before
    assert _kind_tree(root, "outcome") == {}
    assert (root / "HEAD.json").read_bytes() == head_before


def test_outcome_append_enforces_frozen_target_semantics(tmp_path: Path) -> None:
    root = tmp_path / "forward-v1"
    _context, _state_record, _trial_record, _forecast_record, outcome_record = (
        _seed_through_forecast(root)
    )
    forged = json.loads(_canonical(outcome_record))
    forged["outcome_value"]["unit"] = "percent"
    _rehash(forged, field="outcome_record_id", prefix="mmoutcome_")
    before = _tree(root)
    with pytest.raises(
        store.MarketMemoryForwardConflictError, match="forecast event and trial"
    ):
        store.append_outcome(root, forged, observed_now=OBSERVED_NOW)
    assert _tree(root) == before


def test_outcome_corrections_append_and_must_extend_active_revision(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward-v1"
    _context, _state_record, _trial_record, forecast_record, first = (
        _seed_through_forecast(root)
    )
    first_result = store.append_outcome(root, first, observed_now=OBSERVED_NOW)
    first_path = next((root / "objects" / "outcome").glob("*/*.json"))
    first_bytes = first_path.read_bytes()
    same_clock_correction = _outcome(
        forecast_record,
        value=0.013,
        revision_number=2,
        revision_of=first["outcome_record_id"],
    )
    for field in ("source_available_at", "known_at", "observed_at", "recorded_at"):
        same_clock_correction[field] = first[field]
    _rehash(
        same_clock_correction,
        field="outcome_record_id",
        prefix="mmoutcome_",
    )
    before_same_clock = _tree(root)
    with pytest.raises(store.MarketMemoryForwardConflictError, match="active revision"):
        store.append_outcome(
            root,
            same_clock_correction,
            observed_now=CORRECTION_OBSERVED_NOW,
        )
    assert _tree(root) == before_same_clock

    correction = _outcome(
        forecast_record,
        value=0.012,
        revision_number=2,
        revision_of=first["outcome_record_id"],
    )
    second_result = store.append_outcome(
        root, correction, observed_now=CORRECTION_OBSERVED_NOW
    )

    assert first_result.appended and second_result.appended
    assert first_path.read_bytes() == first_bytes
    assert len(list((root / "objects" / "outcome").glob("*/*.json"))) == 2
    assert (
        store.load_record(root, kind="outcome", record_id=first["outcome_record_id"])
        == first
    )
    assert (
        store.load_record(
            root, kind="outcome", record_id=correction["outcome_record_id"]
        )
        == correction
    )
    generation = store.load_generation(root, second_result.generation_id)
    outcomes = [entry for entry in generation["entries"] if entry["kind"] == "outcome"]
    assert [(row["revision_number"], row["revision_of"]) for row in outcomes] == [
        (1, None),
        (2, first["outcome_record_id"]),
    ]

    stale_correction = _outcome(
        forecast_record,
        value=0.011,
        revision_number=2,
        revision_of=first["outcome_record_id"],
    )
    before = _tree(root)
    with pytest.raises(store.MarketMemoryForwardConflictError, match="active revision"):
        store.append_outcome(
            root, stale_correction, observed_now=CORRECTION_OBSERVED_NOW
        )
    assert _tree(root) == before


def test_head_is_last_and_crash_retry_reuses_orphaned_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _initialized_root(tmp_path)
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    genesis_head = (root / "HEAD.json").read_bytes()
    original_replace = store._replace_head

    def crash_before_head(_root: Path, _value: object) -> None:
        raise RuntimeError("simulated crash before HEAD")

    monkeypatch.setattr(store, "_replace_head", crash_before_head)
    with pytest.raises(RuntimeError, match="simulated crash"):
        store.append_state(root, state_record, exact_context_bytes=context_bytes)
    assert (root / "HEAD.json").read_bytes() == genesis_head
    with pytest.raises(store.MarketMemoryForwardStoreError, match="not reachable"):
        store.load_record(
            root, kind="state", record_id=state_record["state_snapshot_id"]
        )
    assert len(list((root / "objects" / "state").glob("*/*.json"))) == 1
    assert len(list((root / "generations").glob("*/*.json"))) == 2

    monkeypatch.setattr(store, "_replace_head", original_replace)
    retried = store.append_state(root, state_record, exact_context_bytes=context_bytes)
    assert retried.appended
    assert (
        store.load_record(
            root, kind="state", record_id=state_record["state_snapshot_id"]
        )
        == state_record
    )


def test_short_write_never_strands_a_partial_final_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _initialized_root(tmp_path)
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    original_write = store.os.write
    writes = 0

    def short_then_fail(descriptor: int, body: bytes) -> int:
        nonlocal writes
        writes += 1
        if writes == 1:
            return original_write(descriptor, body[:17])
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(store.os, "write", short_then_fail)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="durably created"):
        store.append_state(root, state_record, exact_context_bytes=context_bytes)
    state_path = store._record_path(root, "state", state_record["state_snapshot_id"])
    assert not state_path.exists()
    assert not list(root.rglob(".*.tmp"))

    monkeypatch.setattr(store.os, "write", original_write)
    retried = store.append_state(root, state_record, exact_context_bytes=context_bytes)
    assert retried.appended


def test_hard_exit_during_write_is_cleaned_and_exact_retry_succeeds(
    tmp_path: Path,
) -> None:
    root = _initialized_root(tmp_path)
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    context_path = tmp_path / "context.json"
    record_path = tmp_path / "state.json"
    context_path.write_bytes(context_bytes)
    record_path.write_bytes(_canonical(state_record))
    script = """
import json
import os
import sys
from pathlib import Path
from engine.neuralweb import market_memory_forward_store as store

root = Path(sys.argv[1])
context = Path(sys.argv[2]).read_bytes()
record = json.loads(Path(sys.argv[3]).read_bytes())
store.tempfile.gettempdir()
original_write = store.os.write

def crash_write(descriptor, body):
    original_write(descriptor, body[:17])
    os._exit(91)

store.os.write = crash_write
store.append_state(root, record, exact_context_bytes=context)
"""
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(root),
            str(context_path),
            str(record_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert crashed.returncode == 91, crashed.stderr
    final_path = store._record_path(root, "state", state_record["state_snapshot_id"])
    assert not final_path.exists()
    assert list(root.rglob(".*.tmp"))

    retried = store.append_state(root, state_record, exact_context_bytes=context_bytes)
    assert retried.appended
    assert not list(root.rglob(".*.tmp"))
    assert (
        store.load_record(
            root, kind="state", record_id=state_record["state_snapshot_id"]
        )
        == state_record
    )


def test_hard_exit_after_link_publish_recovers_link_count_and_retries(
    tmp_path: Path,
) -> None:
    root = _initialized_root(tmp_path)
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    context_path = tmp_path / "link-context.json"
    record_path = tmp_path / "link-state.json"
    context_path.write_bytes(context_bytes)
    record_path.write_bytes(_canonical(state_record))
    script = """
import json
import os
import sys
from pathlib import Path
from engine.neuralweb import market_memory_forward_store as store

root = Path(sys.argv[1])
context = Path(sys.argv[2]).read_bytes()
record = json.loads(Path(sys.argv[3]).read_bytes())
store.tempfile.gettempdir()
original_link = store.os.link

def crash_link(source, target, **kwargs):
    original_link(source, target, **kwargs)
    os._exit(92)

store.os.link = crash_link
store.append_state(root, record, exact_context_bytes=context)
"""
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(root),
            str(context_path),
            str(record_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert crashed.returncode == 92, crashed.stderr
    final_path = store._record_path(root, "state", state_record["state_snapshot_id"])
    assert final_path.stat().st_nlink == 2

    retried = store.append_state(root, state_record, exact_context_bytes=context_bytes)
    assert retried.appended
    assert final_path.stat().st_nlink == 1
    assert not list(root.rglob(".*.tmp"))


def test_temp_orphan_population_is_hard_bounded(tmp_path: Path) -> None:
    root = _initialized_root(tmp_path)
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    for index in range(store._MAX_ORPHAN_TEMPS + 1):
        orphan = root / f".orphan-{index:03d}.{'a' * 32}.tmp"
        orphan.write_bytes(b"partial")
        orphan.chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="orphan bound"):
        store.append_state(root, state_record, exact_context_bytes=context_bytes)


def test_record_and_generation_are_fsynced_before_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _initialized_root(tmp_path)
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    events: list[str] = []
    fsync_calls = 0
    original_write = store._write_create_once
    original_head = store._replace_head
    original_fsync = store.os.fsync

    def traced_write(path: Path, body: bytes, *, label: str) -> bool:
        result = original_write(path, body, label=label)
        if label == "forward state record":
            events.append("record")
        elif label == "forward generation":
            events.append("generation")
        return result

    def traced_head(path: Path, value: object) -> None:
        events.append("head")
        original_head(path, value)

    def traced_fsync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        original_fsync(descriptor)

    monkeypatch.setattr(store, "_write_create_once", traced_write)
    monkeypatch.setattr(store, "_replace_head", traced_head)
    monkeypatch.setattr(store.os, "fsync", traced_fsync)
    store.append_state(root, state_record, exact_context_bytes=context_bytes)

    assert events == ["record", "generation", "head"]
    assert fsync_calls >= 6


def test_missing_head_never_scans_or_falls_back_to_latest_generation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "forward-v1"
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    (root / "HEAD.json").unlink()

    with pytest.raises(store.MarketMemoryForwardStoreError, match="HEAD is missing"):
        store.initialize_forward_store(root)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="head"):
        # Read APIs require HEAD and cannot infer a newest generation.
        store.load_record(
            root, kind="state", record_id=state_record["state_snapshot_id"]
        )


def test_record_and_old_ancestry_tamper_poison_every_read(tmp_path: Path) -> None:
    root = tmp_path / "forward-v1"
    context_bytes, state_record, trial_record, _forecast_record, _outcome_record = (
        _records()
    )
    first = store.append_state(root, state_record, exact_context_bytes=context_bytes)
    second = store.append_trial(root, trial_record)
    state_path = next((root / "objects" / "state").glob("*/*.json"))
    original_state = state_path.read_bytes()
    state_path.write_bytes(original_state[:-1] + b" ")
    state_path.chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError):
        store.load_record(
            root, kind="trial", record_id=trial_record["trial_registration_id"]
        )
    state_path.write_bytes(original_state)
    state_path.chmod(0o600)

    old_generation = store.load_generation(root, first.generation_id)
    old_path = (
        root
        / "generations"
        / first.generation_id[-64:-62]
        / (first.generation_id + ".json")
    )
    old_generation["replay_digest"] = "0" * 64
    old_path.write_bytes(_canonical(old_generation))
    old_path.chmod(0o600)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="replay digest"):
        store.load_generation(root, second.generation_id)


def test_file_permission_drift_and_wrong_kind_load_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "forward-v1"
    context_bytes = _context_bytes()
    state_record = _state(context_bytes)
    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    state_path = next((root / "objects" / "state").glob("*/*.json"))
    state_path.chmod(0o640)
    with pytest.raises(store.MarketMemoryForwardStoreError, match="private"):
        store.load_record(
            root, kind="state", record_id=state_record["state_snapshot_id"]
        )
    state_path.chmod(0o600)

    with pytest.raises(store.MarketMemoryForwardStoreError, match="malformed"):
        store.load_record(
            root, kind="trial", record_id=state_record["state_snapshot_id"]
        )


def test_record_count_and_byte_bounds_are_hard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context_bytes, state_record, trial_record, _forecast_record, _outcome_record = (
        _records()
    )
    monkeypatch.setattr(store, "_MAX_RECORDS", 2)
    (tmp_path / "count").mkdir(mode=0o700)
    root = tmp_path / "count" / "forward-v1"
    store.append_state(root, state_record, exact_context_bytes=context_bytes)
    store.append_trial(root, trial_record)
    third_trial = _trial(trial_key="synthetic.spy.close.second.v1")
    with pytest.raises(store.MarketMemoryForwardStoreError, match="bound"):
        store.append_trial(root, third_trial)

    monkeypatch.setattr(store, "_MAX_RECORD_BYTES", 100)
    (tmp_path / "bytes").mkdir(mode=0o700)
    tiny_root = tmp_path / "bytes" / "forward-v1"
    with pytest.raises(store.MarketMemoryForwardStoreError, match="byte bound"):
        store.append_state(tiny_root, state_record, exact_context_bytes=context_bytes)
    assert not tiny_root.exists()


def test_replay_digest_is_deterministic_across_store_nonces(tmp_path: Path) -> None:
    first = tmp_path / "a" / "forward-v1"
    second = tmp_path / "b" / "forward-v1"
    first.parent.mkdir(mode=0o700)
    second.parent.mkdir(mode=0o700)
    records = _records()
    context_bytes, state_record, trial_record, forecast_record, outcome_record = records
    results: list[store.ForwardAppendResult] = []
    for root in (first, second):
        store.append_state(root, state_record, exact_context_bytes=context_bytes)
        store.append_trial(root, trial_record)
        store.append_forecast(root, forecast_record, exact_context_bytes=context_bytes)
        results.append(
            store.append_outcome(root, outcome_record, observed_now=OBSERVED_NOW)
        )

    assert results[0].generation_id != results[1].generation_id
    assert results[0].replay_digest == results[1].replay_digest
    assert store.replay_digest(first, results[0].generation_id) == store.replay_digest(
        second, results[1].generation_id
    )
