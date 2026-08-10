"""Adversarial W1B.1 tests for the bounded raw-regime projection."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_projection as projection

ROOT = Path(__file__).resolve().parents[1]
OBSERVED = datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc)
TRANSITION_FLAGS = {
    "flag_breadth_price": False,
    "flag_credit_equity": False,
    "flag_ratio_inflection": False,
    "flag_inflation_basket": False,
    "flag_confidence_decay": True,
    "flag_gex": False,
    "flag_rotation_persistence": True,
}
STATE_FIELDS = {
    "quad",
    "raw_quad",
    "pending_quad",
    "pending_days",
    "pending_need",
    "growth_score",
    "inflation_score",
    "growth_confidence",
    "inflation_confidence",
    "confidence",
    "liquidity_overlay",
    "cycle_tag",
    "transition_state",
    "transition_state_raw",
    "transition_ratcheted",
    "transition_dwell_remaining",
    "transition_flags",
}


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(projection, "_utc_now", lambda: OBSERVED)


def _raw_regime() -> dict:
    return {
        "schema_version": 1,
        "asof": "2026-08-07",
        "date": "2026-08-07",
        "quad": "Q2",
        "quad_name": "Reflation must not project",
        "label": "forbidden label must not project",
        "raw_quad": "Q2",
        "pending_quad": None,
        "pending_days": 0,
        "pending_need": 7,
        "growth_score": 0.133,
        "inflation_score": 0.4,
        "growth_confidence": 0.1,
        "inflation_confidence": 0.3,
        "confidence": 0.2,
        "liquidity_overlay": "contracting",
        "cycle_tag": "late",
        "transition_state": "TRANSITIONING",
        "transition_state_raw": "WEAKENING",
        "transition_ratcheted": True,
        "transition_dwell_remaining": 5,
        "transition_flags": copy.deepcopy(TRANSITION_FLAGS),
        # The real payload contains many such planes.  Projection is an exact
        # allowlist rather than a recursive copy with a fragile denylist.
        "ignored_recursive_planes": {
            "label": "winner",
            "outcome": {"forward_return": 0.9},
            "options": [{"rank": 1, "trade": True}],
            "Prophet": {"gate": True, "size": 1.0},
        },
        "freshness": {
            "asof": "2026-08-07",
            "built_at": "2026-08-10T01:52:29Z",
            "stale": False,
        },
    }


def _write_source(path: Path, payload: dict | None = None) -> bytes:
    body = (
        json.dumps(
            payload if payload is not None else _raw_regime(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    path.write_bytes(body)
    return body


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content(snapshot: dict) -> dict:
    return {
        "schema": snapshot["schema"],
        "as_of": snapshot["as_of"],
        "transform_version": snapshot["transform_version"],
        "source_artifact": snapshot["source_artifact"],
        "state": snapshot["state"],
    }


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def test_builder_binds_exact_raw_and_projected_bytes_and_returns_typed_reference(
    tmp_path: Path,
) -> None:
    source = tmp_path / "latest.json"
    raw_body = _write_source(source)

    snapshot = projection.build_macro_regime_snapshot(source)
    content = _canonical(_content(snapshot))

    assert snapshot["schema"] == projection.SNAPSHOT_SCHEMA
    assert snapshot["transform_version"] == projection.TRANSFORM_VERSION
    assert snapshot["pit_basis"] == "live_captured"
    assert snapshot["as_of"] == "2026-08-10T01:52:29Z"
    assert snapshot["observed_at"] == "2026-08-10T03:00:00Z"
    assert "available_at" not in snapshot
    assert snapshot["source_artifact"] == {
        "source_id": "data.regime.latest",
        "source_schema_version": 1,
        "source_asof": "2026-08-07",
        "built_at": "2026-08-10T01:52:29Z",
        "raw_sha256": hashlib.sha256(raw_body).hexdigest(),
        "raw_bytes": len(raw_body),
    }
    assert snapshot["content_sha256"] == hashlib.sha256(content).hexdigest()
    assert snapshot["content_bytes"] == len(content)
    assert snapshot["snapshot_id"] == "mmsnap_" + snapshot["content_sha256"]
    assert snapshot["authority"] == dict(market_memory.AUTHORITY)
    assert snapshot["quality"] == {
        "status": "complete",
        "actual_output_capture": True,
        "current_snapshot_only": True,
        "component_source_receipts_authenticated": False,
        "feature_projection_eligible": True,
        "imputed": False,
        "training_eligible": False,
        "promotion_eligible": False,
    }
    assert projection.macro_regime_snapshot_reference(snapshot) == {
        "snapshot_id": snapshot["snapshot_id"],
        "schema": projection.SNAPSHOT_SCHEMA,
        "content_sha256": snapshot["content_sha256"],
        "as_of": snapshot["as_of"],
    }
    assert projection.read_verified_macro_regime_bytes(source, snapshot) == raw_body


def test_projection_is_an_exact_small_allowlist_without_recursive_decision_or_label_planes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    snapshot = projection.build_macro_regime_snapshot(source)

    assert set(snapshot["state"]) == STATE_FIELDS
    assert snapshot["state"]["transition_flags"] == TRANSITION_FLAGS
    projected_keys = {key.lower() for key in _all_keys(snapshot["state"])}
    forbidden = {
        "label",
        "outcome",
        "forward_return",
        "options",
        "prophet",
        "rank",
        "gate",
        "size",
        "trade",
    }
    assert projected_keys.isdisjoint(forbidden)
    assert len(_canonical(snapshot["state"])) < 2_048


def test_snapshot_schema_is_strict_and_accepts_the_builder(tmp_path: Path) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    snapshot = projection.build_macro_regime_snapshot(source)
    schema = json.loads(
        (
            ROOT / "contracts/market_memory/macro_regime_snapshot.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(snapshot)

    mutants = []
    extra = copy.deepcopy(snapshot)
    extra["future_field"] = True
    mutants.append(extra)
    label = copy.deepcopy(snapshot)
    label["state"]["label"] = "winner"
    mutants.append(label)
    authority = copy.deepcopy(snapshot)
    authority["authority"]["may_rank"] = True
    mutants.append(authority)
    training = copy.deepcopy(snapshot)
    training["quality"]["training_eligible"] = True
    mutants.append(training)
    backdated = copy.deepcopy(snapshot)
    backdated["source_artifact"]["available_at"] = backdated["as_of"]
    mutants.append(backdated)

    for mutant in mutants:
        with pytest.raises(ValidationError):
            validator.validate(mutant)


@pytest.mark.parametrize(
    "body",
    [
        b'{"schema_version":1,"quad":"Q2","quad":"Q3"}',
        b'{"schema_version":1,"nested":{"x":1,"x":2}}',
        b'{"schema_version":1,"ignored":NaN}',
        b'{"schema_version":1,"ignored":Infinity}',
        b'{"schema_version":1,"ignored":-Infinity}',
        b"[]",
        b"{broken",
    ],
)
def test_strict_json_rejects_duplicates_nonfinite_tokens_and_nonobjects(
    tmp_path: Path, body: bytes
) -> None:
    source = tmp_path / "latest.json"
    source.write_bytes(body)
    with pytest.raises(
        projection.MarketMemoryProjectionError, match="strict JSON|object"
    ):
        projection.build_macro_regime_snapshot(source)


def test_source_size_regular_file_and_symlink_bounds(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    with pytest.raises(projection.MarketMemoryProjectionError, match="size bound"):
        projection.build_macro_regime_snapshot(empty)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(projection.MarketMemoryProjectionError, match="size bound"):
        projection.build_macro_regime_snapshot(oversized)

    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(projection.MarketMemoryProjectionError, match="regular file"):
        projection.build_macro_regime_snapshot(directory)

    target = tmp_path / "target.json"
    _write_source(target)
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(target)
    with pytest.raises(projection.MarketMemoryProjectionError, match="symlink|safely"):
        projection.build_macro_regime_snapshot(symlink)


def test_atomic_path_replacement_during_read_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    replacement = tmp_path / "replacement.json"
    changed = _raw_regime()
    changed["growth_score"] = 0.2
    _write_source(replacement, changed)
    original_read = projection.os.read
    replaced = False

    def racing_read(descriptor: int, count: int) -> bytes:
        nonlocal replaced
        chunk = original_read(descriptor, count)
        if chunk and not replaced:
            replaced = True
            replacement.replace(source)
        return chunk

    monkeypatch.setattr(projection.os, "read", racing_read)
    with pytest.raises(projection.MarketMemoryProjectionError, match="changed"):
        projection.build_macro_regime_snapshot(source)


def test_observation_clock_is_process_owned_and_called_only_after_stable_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    events: list[str] = []
    original_read = projection._stable_read_source

    def traced_read(path):
        result = original_read(path)
        events.append("stable-read-complete")
        return result

    def traced_clock() -> datetime:
        events.append("clock")
        return OBSERVED

    monkeypatch.setattr(projection, "_stable_read_source", traced_read)
    monkeypatch.setattr(projection, "_utc_now", traced_clock)
    projection.build_macro_regime_snapshot(source)

    assert events == ["stable-read-complete", "clock"]
    assert (
        "observed_at"
        not in inspect.signature(projection.build_macro_regime_snapshot).parameters
    )


def test_content_identity_is_stable_across_later_observation_clocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    first = projection.build_macro_regime_snapshot(source)
    monkeypatch.setattr(
        projection,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 4, 0, tzinfo=timezone.utc),
    )
    second = projection.build_macro_regime_snapshot(source)

    assert second["observed_at"] == "2026-08-10T04:00:00Z"
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["content_sha256"] == first["content_sha256"]
    assert second["content_bytes"] == first["content_bytes"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("asof", "2026-08-11", "future"),
        ("date", "2026-08-08", "does not match"),
    ],
)
def test_asof_and_date_must_be_causal_and_consistent(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    raw = _raw_regime()
    raw[field] = value
    if field == "asof":
        raw["date"] = value
        raw["freshness"]["asof"] = value
        raw["freshness"]["built_at"] = f"{value}T01:00:00Z"
    source = tmp_path / "latest.json"
    _write_source(source, raw)
    with pytest.raises(projection.MarketMemoryProjectionError, match=message):
        projection.build_macro_regime_snapshot(source)


def test_freshness_built_at_is_measurement_only_and_must_not_be_future(
    tmp_path: Path,
) -> None:
    raw = _raw_regime()
    raw["freshness"]["built_at"] = "2026-08-10T03:00:01Z"
    source = tmp_path / "latest.json"
    _write_source(source, raw)
    with pytest.raises(projection.MarketMemoryProjectionError, match="future"):
        projection.build_macro_regime_snapshot(source)

    raw = _raw_regime()
    raw["freshness"]["built_at"] = "2026-08-06T23:59:59Z"
    _write_source(source, raw)
    with pytest.raises(projection.MarketMemoryProjectionError, match="asof follows"):
        projection.build_macro_regime_snapshot(source)


def test_source_semantics_and_allowlisted_types_fail_closed(tmp_path: Path) -> None:
    mutations = [
        ("schema_version", True),
        ("growth_score", float("inf")),
        ("confidence", 1.01),
        ("transition_ratcheted", 1),
        ("pending_days", True),
    ]
    for index, (field, value) in enumerate(mutations):
        raw = _raw_regime()
        raw[field] = value
        source = tmp_path / f"bad-{index}.json"
        # Infinity here deliberately reaches the strict JSON guard first.
        source.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(projection.MarketMemoryProjectionError):
            projection.build_macro_regime_snapshot(source)

    raw = _raw_regime()
    raw["transition_flags"]["rank"] = True
    source = tmp_path / "extra-flag.json"
    _write_source(source, raw)
    with pytest.raises(projection.MarketMemoryProjectionError, match="allowlist"):
        projection.build_macro_regime_snapshot(source)


def test_pending_hysteresis_state_is_not_silently_normalized(tmp_path: Path) -> None:
    source = tmp_path / "latest.json"
    raw = _raw_regime()
    raw["pending_days"] = 1
    _write_source(source, raw)
    with pytest.raises(projection.MarketMemoryProjectionError, match="pending_days"):
        projection.build_macro_regime_snapshot(source)

    raw = _raw_regime()
    raw.update({"pending_quad": "Q3", "pending_days": 7, "pending_need": 7})
    _write_source(source, raw)
    with pytest.raises(projection.MarketMemoryProjectionError, match="hysteresis"):
        projection.build_macro_regime_snapshot(source)


def test_validator_recomputes_content_hash_bytes_clock_and_authority(
    tmp_path: Path,
) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    snapshot = projection.build_macro_regime_snapshot(source)

    mutants = []
    state = copy.deepcopy(snapshot)
    state["state"]["growth_score"] = 0.2
    mutants.append(state)
    size = copy.deepcopy(snapshot)
    size["content_bytes"] += 1
    mutants.append(size)
    clock = copy.deepcopy(snapshot)
    clock["observed_at"] = "2026-08-10T01:52:28Z"
    mutants.append(clock)
    quality = copy.deepcopy(snapshot)
    quality["quality"]["promotion_eligible"] = True
    mutants.append(quality)
    authority = copy.deepcopy(snapshot)
    authority["authority"]["may_trade"] = True
    mutants.append(authority)
    source_extra = copy.deepcopy(snapshot)
    source_extra["source_artifact"]["available_at"] = snapshot["observed_at"]
    mutants.append(source_extra)

    for mutant in mutants:
        with pytest.raises(projection.MarketMemoryProjectionError):
            projection.validate_macro_regime_snapshot(mutant)


def test_validation_and_reference_return_detached_values(tmp_path: Path) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    snapshot = projection.build_macro_regime_snapshot(source)
    clean = projection.validate_macro_regime_snapshot(snapshot)
    reference = projection.macro_regime_snapshot_reference(snapshot)

    snapshot["state"]["quad"] = "Q4"
    snapshot["source_artifact"]["source_asof"] = "2000-01-01"
    assert clean["state"]["quad"] == "Q2"
    assert clean["source_artifact"]["source_asof"] == "2026-08-07"
    assert reference["snapshot_id"] == clean["snapshot_id"]


def test_verified_raw_read_closes_projection_to_persistence_replacement_race(
    tmp_path: Path,
) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    snapshot = projection.build_macro_regime_snapshot(source)

    # Semantically identical JSON with different whitespace is still different
    # exact evidence and cannot be persisted under the first raw byte receipt.
    source.write_text(json.dumps(_raw_regime(), sort_keys=True), encoding="utf-8")
    with pytest.raises(projection.MarketMemoryProjectionError, match="no longer match"):
        projection.read_verified_macro_regime_bytes(source, snapshot)


def test_builder_is_read_only_and_creates_no_store_or_packet(tmp_path: Path) -> None:
    source = tmp_path / "latest.json"
    _write_source(source)
    before = sorted(path.name for path in tmp_path.iterdir())
    projection.build_macro_regime_snapshot(source)
    after = sorted(path.name for path in tmp_path.iterdir())
    assert after == before == ["latest.json"]


def test_committed_regime_artifact_fails_closed_while_it_contains_nonfinite_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = ROOT / "data/regime/latest.json"
    body = source.read_bytes()
    if any(token in body for token in (b"NaN", b"Infinity")):
        with pytest.raises(projection.MarketMemoryProjectionError, match="strict JSON"):
            projection.build_macro_regime_snapshot(source)
    else:
        # This branch becomes the live canary when the upstream producer is
        # hardened; the test need not be rewritten merely because source debt
        # was removed.
        monkeypatch.setattr(projection, "_utc_now", lambda: datetime.now(timezone.utc))
        projection.validate_macro_regime_snapshot(
            projection.build_macro_regime_snapshot(source)
        )
