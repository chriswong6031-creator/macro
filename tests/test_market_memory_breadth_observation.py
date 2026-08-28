"""Adversarial tests for the clock-free W1B.3A breadth projector."""

from __future__ import annotations

import copy
import functools
import hashlib
import io
import json
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, ValidationError

from engine.neuralweb import market_memory_breadth_observation as breadth
from lib import nyse_calendar

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_V1 = {
    "tier": "display",
    "horizon_role": "context",
    "context_only": True,
    "proposal_weight": 0,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "may_trade": False,
    "may_originate": False,
    "may_select_options_candidate": False,
    "may_execute": False,
    "may_write_options_episode": False,
    "may_append_outcome": False,
    "may_train_prophet": False,
}
SOURCE_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/breadth_source_observation.v1.schema.json"
)
SNAPSHOT_SCHEMA_PATH = (
    ROOT / "contracts/market_memory/breadth_factors_snapshot.v1.schema.json"
)
_FROZEN_FIXTURE_SESSION = "2026-08-07"
# Both fixture bodies are byte-pinned captures from the SAME nightly commit
# (448cfacc0957, collection 2026-08-10). Truncating the live ledger is not
# stable: the nightly revises historical rows (n_members@2026-08-07 read 502
# at capture time and 504 eleven days later), and the live constituents file
# moves on every index reconstitution. Numerator and denominator must come
# from the same era or the coverage bound asserts on a ratio no real run
# ever produced. Advance both files together, never one.
_FROZEN_BREADTH_FIXTURE = (
    ROOT / "tests/fixtures/market_memory/breadth_through_2026-08-07.parquet"
)
_FROZEN_CONSTITUENTS_FIXTURE = (
    ROOT / "tests/fixtures/market_memory/constituents_2026-08-07.parquet"
)


def _git_blob_oid(body: bytes) -> str:
    framed = f"blob {len(body)}\0".encode("ascii") + body
    return hashlib.sha1(framed).hexdigest()


@functools.lru_cache(maxsize=1)
def _frozen_breadth_body() -> bytes:
    """Detach the unit fixture from the nightly-revised repository ledger."""

    body = _FROZEN_BREADTH_FIXTURE.read_bytes()
    frame = pd.read_parquet(io.BytesIO(body), engine="pyarrow")
    assert frame.index[-1].date().isoformat() == _FROZEN_FIXTURE_SESSION
    return body


def _inputs(
    *,
    breadth_body: bytes | None = None,
    constituents_body: bytes | None = None,
    canary_config_body: bytes | None = None,
    calendar_module_body: bytes | None = None,
    pinned_commit: str = "1" * 40,
) -> breadth.PinnedBreadthInputs:
    bodies = {
        "breadth_actual_output": _frozen_breadth_body()
        if breadth_body is None
        else breadth_body,
        "current_constituents": _FROZEN_CONSTITUENTS_FIXTURE.read_bytes()
        if constituents_body is None
        else constituents_body,
        "canary_identity_config": (
            ROOT / "config/market_memory_canary.v1.json"
        ).read_bytes()
        if canary_config_body is None
        else canary_config_body,
        "xnys_calendar_module": (ROOT / "lib/nyse_calendar.py").read_bytes()
        if calendar_module_body is None
        else calendar_module_body,
    }
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


def _breadth_frame(body: bytes | None = None) -> pd.DataFrame:
    source = _inputs().breadth_body if body is None else body
    return pd.read_parquet(io.BytesIO(source), engine="pyarrow")


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, engine="pyarrow", index=True)
    return buffer.getvalue()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def _run_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _create_source_repository(path: Path) -> str:
    for repo_path in (
        "data/breadth/breadth.parquet",
        "data/breadth/constituents.parquet",
        "config/market_memory_canary.v1.json",
        "lib/nyse_calendar.py",
    ):
        target = path / repo_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / repo_path).read_bytes())
    _run_git(path, "init", "-q")
    _run_git(path, "config", "user.email", "market-memory@example.invalid")
    _run_git(path, "config", "user.name", "Market Memory Test")
    _run_git(path, "add", "--", "data", "config", "lib")
    _run_git(path, "commit", "-q", "-m", "fixture")
    return _run_git(path, "rev-parse", "HEAD")


def test_projector_emits_exact_clock_free_current_tip_bundle() -> None:
    repo_tip_body = (ROOT / "data/breadth/breadth.parquet").read_bytes()
    inputs = _inputs(breadth_body=repo_tip_body)
    bundle = breadth.project_current_breadth_snapshot(inputs)
    frame = _breadth_frame(repo_tip_body)
    tip = frame.iloc[-1]
    session = frame.index[-1].date().isoformat()
    constituent_count = len(
        pd.read_parquet(io.BytesIO(inputs.constituents_body), engine="pyarrow")
    )

    assert bundle.source_observation == {
        "schema": breadth.SOURCE_OBSERVATION_SCHEMA,
        "source_observation_id": bundle.source_observation["source_observation_id"],
        "profile": "sp500_current_membership_breadth.v1",
        "session": session,
        "sources": bundle.source_observation["sources"],
        "temporal_policy": {
            "current_tip_only": True,
            "historical_rows_operational": False,
            "availability_clock_owner": "private_breadth_store_first_durable_write",
            "projector_samples_clock": False,
        },
        "limitations": {
            "current_membership_only": True,
            "current_membership_survivor_bias": True,
            "historical_constituent_point_in_time": False,
            "calendar_coverage": "full_day_closures_only",
            "calendar_partial_coverage": True,
            "ad_line_excluded": True,
        },
        "authority": copy.deepcopy(AUTHORITY_V1),
    }
    assert set(bundle.source_observation["sources"]) == {
        "breadth_actual_output",
        "current_constituents",
        "canary_identity_config",
        "xnys_calendar_module",
    }
    assert bundle.source_observation_bytes == _canonical(bundle.source_observation)
    assert bundle.feature_object_bytes == _canonical(bundle.feature_object)
    assert bundle.feature_object["schema"] == breadth.SNAPSHOT_SCHEMA
    assert bundle.feature_object["session"] == session
    assert bundle.feature_object["state"] == {
        "n_members": int(tip["n_members"]),
        "constituent_count": constituent_count,
        "priced_member_coverage": int(tip["n_members"]) / constituent_count,
        "pct_above_50": float(tip["pct_above_50"]),
        "pct_above_200": float(tip["pct_above_200"]),
        "new_highs": int(tip["nh"]),
        "new_lows": int(tip["nl"]),
        "advancers": int(tip["adv"]),
        "decliners": int(tip["dec"]),
    }
    assert bundle.feature_object["authority"] == AUTHORITY_V1
    assert bundle.feature_object["quality"]["actual_output_source"] is True
    assert "actual_output_capture" not in bundle.feature_object["quality"]
    assert bundle.feature_object["quality"]["training_eligible"] is False
    assert bundle.feature_object["quality"]["promotion_eligible"] is False
    keys = _all_keys(
        {"source": bundle.source_observation, "feature": bundle.feature_object}
    )
    assert {
        "observed_at",
        "available_at",
        "event_time",
        "measurement_end",
        "ad_line",
        "label",
        "outcome",
        "forward_return",
        "prophet",
        "rank",
        "gate",
        "trade",
    }.isdisjoint({key.lower() for key in keys})


def test_ids_bind_only_the_frozen_source_and_feature_identity_cores() -> None:
    inputs = _inputs(pinned_commit="1" * 40)
    first = breadth.project_current_breadth_snapshot(inputs)
    second = breadth.project_current_breadth_snapshot(
        replace(inputs, pinned_commit="2" * 40)
    )

    assert first.source_observation == second.source_observation
    assert first.feature_object == second.feature_object
    assert ("1" * 40).encode() not in first.source_observation_bytes
    assert ("1" * 40).encode() not in first.feature_object_bytes

    source_core = {
        "profile": breadth.PROFILE,
        "session": first.source_observation["session"],
        "source_sha256": {
            role: artifact["sha256"]
            for role, artifact in first.source_observation["sources"].items()
        },
    }
    assert first.source_observation["source_observation_id"] == (
        "mmbreadthsrc_" + hashlib.sha256(_canonical(source_core)).hexdigest()
    )
    feature_core = {
        "source_observation_id": first.source_observation["source_observation_id"],
        "transform_version": breadth.TRANSFORM_VERSION,
        "semantic_value": first.feature_object["state"],
    }
    assert first.feature_object["snapshot_id"] == (
        "mmsnap_" + hashlib.sha256(_canonical(feature_core)).hexdigest()
    )


def test_frozen_v1_calendar_has_full_daily_parity_and_explicit_support_bounds() -> None:
    calendar_body = (ROOT / "lib/nyse_calendar.py").read_bytes()
    assert hashlib.sha256(calendar_body).hexdigest() == (
        "7c9167fd416babb64c3067ae7e6237615011ad79e26d826e57005486496410ce"
    )

    cursor = date(1962, 1, 1)
    end = date(2100, 12, 31)
    while cursor <= end:
        assert breadth.is_frozen_v1_xnys_session(cursor) == nyse_calendar.is_session(
            cursor
        )
        cursor += timedelta(days=1)

    for closure in (
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2018, 12, 5),
        date(2025, 1, 9),
    ):
        assert not breadth.is_frozen_v1_xnys_session(closure)
    for unsupported in (date(1961, 12, 31), date(2101, 1, 1)):
        with pytest.raises(
            breadth.MarketMemoryBreadthObservationError, match="1962 through 2100"
        ):
            breadth.is_frozen_v1_xnys_session(unsupported)

    assert breadth.last_frozen_v1_xnys_session_on_or_before(date(2026, 8, 9)) == date(
        2026, 8, 7
    )
    assert breadth.last_frozen_v1_xnys_session_on_or_before(date(2012, 10, 30)) == date(
        2012, 10, 26
    )
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="1962 through 2100"
    ):
        breadth.last_frozen_v1_xnys_session_on_or_before(date(2101, 1, 1))


def test_frozen_v1_config_and_module_remove_mutable_policy_dependencies() -> None:
    config_body = (ROOT / "config/market_memory_canary.v1.json").read_bytes()
    assert hashlib.sha256(config_body).hexdigest() == (
        "5e7823e48866b2c0828122b65f684ed5872c6816a6224f61e44db4c03d129b33"
    )
    module_source = (
        ROOT / "engine/neuralweb/market_memory_breadth_observation.py"
    ).read_text(encoding="utf-8")
    assert "market_memory_identity" not in module_source
    assert "market_memory.AUTHORITY" not in module_source
    assert "nyse_calendar.is_session" not in module_source

    valid = _inputs()
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="calendar module.*SHA-256"
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(calendar_module_body=valid.calendar_module_body + b"\n")
        )


def test_historical_rows_are_not_projected_and_ad_line_is_always_excluded() -> None:
    original = breadth.project_current_breadth_snapshot(_inputs())
    frame = _breadth_frame()
    frame.iloc[0, frame.columns.get_loc("ad_line")] += 123_456
    changed = breadth.project_current_breadth_snapshot(
        _inputs(breadth_body=_parquet_bytes(frame))
    )

    assert changed.feature_object["state"] == original.feature_object["state"]
    assert (
        changed.source_observation["source_observation_id"]
        != (original.source_observation["source_observation_id"])
    )
    assert (
        changed.feature_object["snapshot_id"]
        != (original.feature_object["snapshot_id"])
    )
    assert "ad_line" not in changed.feature_object["state"]
    assert changed.feature_object["limitations"] == {
        "current_membership_only": True,
        "current_membership_survivor_bias": True,
        "historical_constituent_point_in_time": False,
        "calendar_coverage": "full_day_closures_only",
        "calendar_partial_coverage": True,
        "ad_line_excluded": True,
    }


def test_source_and_snapshot_schemas_are_strict() -> None:
    bundle = breadth.project_current_breadth_snapshot(_inputs())
    source_schema = json.loads(SOURCE_SCHEMA_PATH.read_text(encoding="utf-8"))
    snapshot_schema = json.loads(SNAPSHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(source_schema)
    Draft202012Validator.check_schema(snapshot_schema)
    source_validator = Draft202012Validator(source_schema)
    snapshot_validator = Draft202012Validator(snapshot_schema)
    source_validator.validate(bundle.source_observation)
    snapshot_validator.validate(bundle.feature_object)

    source_mutants = []
    source_clock = copy.deepcopy(bundle.source_observation)
    source_clock["observed_at"] = "2026-08-07T20:00:00Z"
    source_mutants.append(source_clock)
    source_history = copy.deepcopy(bundle.source_observation)
    source_history["temporal_policy"]["historical_rows_operational"] = True
    source_mutants.append(source_history)
    source_authority = copy.deepcopy(bundle.source_observation)
    source_authority["authority"]["may_rank"] = True
    source_mutants.append(source_authority)
    for mutant in source_mutants:
        with pytest.raises(ValidationError):
            source_validator.validate(mutant)

    snapshot_mutants = []
    snapshot_ad_line = copy.deepcopy(bundle.feature_object)
    snapshot_ad_line["state"]["ad_line"] = 7207
    snapshot_mutants.append(snapshot_ad_line)
    snapshot_clock = copy.deepcopy(bundle.feature_object)
    snapshot_clock["available_at"] = "2026-08-07T20:00:00Z"
    snapshot_mutants.append(snapshot_clock)
    snapshot_promotion = copy.deepcopy(bundle.feature_object)
    snapshot_promotion["quality"]["promotion_eligible"] = True
    snapshot_mutants.append(snapshot_promotion)
    snapshot_authority = copy.deepcopy(bundle.feature_object)
    snapshot_authority["authority"]["may_train_prophet"] = True
    snapshot_mutants.append(snapshot_authority)
    for mutant in snapshot_mutants:
        with pytest.raises(ValidationError):
            snapshot_validator.validate(mutant)


def test_consumer_boundary_reprojects_raw_cas_and_rejects_every_tamper() -> None:
    bundle = breadth.project_current_breadth_snapshot(_inputs())
    validated = breadth.validate_breadth_snapshot_bundle(bundle)
    assert validated == bundle
    assert validated is not bundle
    assert validated.source_observation is not bundle.source_observation

    altered_source = copy.deepcopy(bundle.source_observation)
    altered_source["limitations"]["ad_line_excluded"] = False
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="noncanonical or tampered"
    ):
        breadth.validate_breadth_snapshot_bundle(
            replace(bundle, source_observation=altered_source)
        )

    altered_feature = copy.deepcopy(bundle.feature_object)
    altered_feature["state"]["new_highs"] += 1
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="noncanonical or tampered"
    ):
        breadth.validate_breadth_snapshot_bundle(
            replace(bundle, feature_object=altered_feature)
        )

    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="source observation bytes"
    ):
        breadth.validate_breadth_snapshot_bundle(
            replace(
                bundle, source_observation_bytes=bundle.source_observation_bytes + b"\n"
            )
        )
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="feature object bytes"
    ):
        breadth.validate_breadth_snapshot_bundle(
            replace(bundle, feature_object_bytes=bundle.feature_object_bytes + b"\n")
        )

    raw_tamper = bytearray(bundle.pinned_inputs.breadth_body)
    raw_tamper[-1] ^= 1
    tampered_inputs = replace(
        bundle.pinned_inputs,
        breadth_body=bytes(raw_tamper),
    )
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="Git blob ID"
    ):
        breadth.validate_breadth_snapshot_bundle(
            replace(bundle, pinned_inputs=tampered_inputs)
        )


def test_reader_requires_exact_current_git_tip_and_rejects_dirty_bytes_and_symlinks(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    commit = _create_source_repository(repository)

    pinned = breadth.read_pinned_breadth_inputs(
        repository,
        pinned_commit=commit,
    )
    assert pinned.pinned_commit == commit
    pinned_frame = pd.read_parquet(io.BytesIO(pinned.breadth_body), engine="pyarrow")
    pinned_tip_session = pinned_frame.index[-1].date().isoformat()
    assert (
        breadth.project_current_breadth_snapshot(pinned).feature_object["session"]
        == pinned_tip_session
    )

    breadth_path = repository / "data/breadth/breadth.parquet"
    original_breadth = breadth_path.read_bytes()
    breadth_path.write_bytes(original_breadth + b"tamper")
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="differ from the pinned"
    ):
        breadth.read_pinned_breadth_inputs(repository, pinned_commit=commit)
    breadth_path.write_bytes(original_breadth)

    constituents_path = repository / "data/breadth/constituents.parquet"
    constituents_path.unlink()
    constituents_path.symlink_to(ROOT / "data/breadth/constituents.parquet")
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="regular non-symlink"
    ):
        breadth.read_pinned_breadth_inputs(repository, pinned_commit=commit)

    constituents_path.unlink()
    constituents_path.write_bytes(
        (ROOT / "data/breadth/constituents.parquet").read_bytes()
    )
    (repository / "unrelated.txt").write_text("next\n", encoding="utf-8")
    _run_git(repository, "add", "--", "unrelated.txt")
    _run_git(repository, "commit", "-q", "-m", "advance")
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="not the current"
    ):
        breadth.read_pinned_breadth_inputs(repository, pinned_commit=commit)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_session", "duplicated"),
        ("nonfinite_tip", "non-finite"),
        ("non_session_tip", "not an XNYS"),
        ("bad_dtype", "noncanonical dtype"),
        ("bad_coverage", "priced-member coverage"),
    ],
)
def test_breadth_parquet_session_numeric_and_coverage_gates(
    mutation: str,
    message: str,
) -> None:
    frame = _breadth_frame()
    if mutation == "duplicate_session":
        frame = pd.concat([frame, frame.tail(1)])
    elif mutation == "nonfinite_tip":
        frame.iloc[-1, frame.columns.get_loc("pct_above_50")] = float("nan")
    elif mutation == "non_session_tip":
        index = frame.index.to_list()
        index[-1] = pd.Timestamp("2026-08-08")
        frame.index = pd.DatetimeIndex(index, name="Date")
    elif mutation == "bad_dtype":
        frame["adv"] = frame["adv"].astype(float)
    elif mutation == "bad_coverage":
        frame.iloc[-1, frame.columns.get_loc("n_members")] = 450
        frame.iloc[-1, frame.columns.get_loc("adv")] = 250
        frame.iloc[-1, frame.columns.get_loc("dec")] = 180
    else:  # pragma: no cover - parametrization is closed above
        raise AssertionError(mutation)

    with pytest.raises(breadth.MarketMemoryBreadthObservationError, match=message):
        breadth.project_current_breadth_snapshot(
            _inputs(breadth_body=_parquet_bytes(frame))
        )


def test_malformed_parquet_exact_byte_types_config_and_calendar_fail_closed() -> None:
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="readable bounded parquet"
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(breadth_body=b"PAR1not-a-parquet-objectPAR1")
        )

    valid = _inputs()
    bytearray_input = replace(
        valid,
        breadth_body=bytearray(valid.breadth_body),  # type: ignore[arg-type]
    )
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="exact immutable bytes"
    ):
        breadth.project_current_breadth_snapshot(bytearray_input)

    config = json.loads(valid.canary_config_body)
    config["authority"]["may_gate"] = True
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="config.*SHA-256"
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(canary_config_body=_canonical(config))
        )

    duplicate_config = valid.canary_config_body.replace(
        b'"schema": "market_memory.canary_identity_config.v1",',
        b'"schema": "market_memory.canary_identity_config.v1",\n  "schema": "duplicate",',
        1,
    )
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="config.*SHA-256"
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(canary_config_body=duplicate_config)
        )

    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="calendar module.*SHA-256"
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(calendar_module_body=b"def is_session(:\n")
        )


def test_parquet_preflight_rejects_compressed_bomb_before_materialization() -> None:
    frame = pd.read_parquet(io.BytesIO(_inputs().constituents_body), engine="pyarrow")
    for offset in range(len(frame)):
        frame.iloc[offset, frame.columns.get_loc("name")] = (
            f"{offset:04d}:" + chr(65 + offset % 26) * 8_192
        )
    body = _parquet_bytes(frame)
    assert len(body) < 2 * 1024 * 1024

    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError,
        match="total uncompressed byte bound",
    ):
        breadth.project_current_breadth_snapshot(_inputs(constituents_body=body))


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("name", "é" * 257),
        ("sector", "界" * 43),
    ],
)
def test_constituent_strings_have_post_decode_utf8_byte_caps(
    column: str,
    value: str,
) -> None:
    frame = pd.read_parquet(io.BytesIO(_inputs().constituents_body), engine="pyarrow")
    frame.iloc[0, frame.columns.get_loc(column)] = value
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError,
        match=rf"{column} exceeds its UTF-8 byte bound",
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(constituents_body=_parquet_bytes(frame))
        )


def test_constituent_duplicates_nulls_and_impossible_coverage_fail_closed() -> None:
    valid = _inputs()
    frame = pd.read_parquet(io.BytesIO(valid.constituents_body), engine="pyarrow")

    duplicate = pd.concat([frame, frame.head(1)])
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="missing or duplicated"
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(constituents_body=_parquet_bytes(duplicate))
        )

    null = frame.copy()
    null.iloc[0, null.columns.get_loc("name")] = None
    with pytest.raises(breadth.MarketMemoryBreadthObservationError, match="nulls"):
        breadth.project_current_breadth_snapshot(
            _inputs(constituents_body=_parquet_bytes(null))
        )

    too_few = frame.iloc[:300].copy()
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="count is outside"
    ):
        breadth.project_current_breadth_snapshot(
            _inputs(constituents_body=_parquet_bytes(too_few))
        )


def test_git_blob_order_duplicates_and_body_binding_are_strict() -> None:
    valid = _inputs()
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="role/OID pairs"
    ):
        breadth.project_current_breadth_snapshot(
            replace(valid, git_blob_oids=(("breadth_actual_output",),))  # type: ignore[arg-type]
        )

    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="out of order"
    ):
        breadth.project_current_breadth_snapshot(
            replace(valid, git_blob_oids=tuple(reversed(valid.git_blob_oids)))
        )

    wrong_oid = list(valid.git_blob_oids)
    wrong_oid[0] = (wrong_oid[0][0], "f" * 40)
    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="does not bind"
    ):
        breadth.project_current_breadth_snapshot(
            replace(valid, git_blob_oids=tuple(wrong_oid))
        )

    with pytest.raises(
        breadth.MarketMemoryBreadthObservationError, match="commit is malformed"
    ):
        breadth.project_current_breadth_snapshot(replace(valid, pinned_commit="HEAD"))
