"""Hostile and conformance tests for the first production-record admission."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine import options_signal_episode
from engine.neuralweb import market_memory_production_records as records
from lib import nyse_calendar
from scripts import capture_market_memory_options_episodes as capture_cli

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "options_signal_episode" / "episodes.jsonl"
SCHEMA = (
    ROOT
    / "contracts"
    / "market_memory"
    / "options_signal_episode_production_record.v1.schema.json"
)
BASE_CAPTURE = datetime(2026, 8, 11, 12, 2, 48, tzinfo=timezone.utc)
FORWARD_CAPTURE = datetime(2026, 8, 12, 12, 2, 48, tzinfo=timezone.utc)
COMMIT = "a" * 40


@contextmanager
def _clock(now: datetime):
    with patch.object(records, "_utc_now", return_value=now):
        yield


def _store(tmp_path: Path) -> Path:
    return tmp_path.resolve() / "production-record-options-episode-v1"


def _canonical_jsonl(rows: list[dict]) -> bytes:
    return b"".join(records._canonical_bytes(row) + b"\n" for row in rows)


def _activation_body() -> bytes:
    """The owner ledger AS OF the activation watermark, not as of tonight.

    ``data/options_signal_episode/episodes.jsonl`` is an append-only production
    ledger the options PIT lane extends every night, but every capture in this
    module is pinned to the activation clock (``records.CONTRACT_FROZEN_AT`` ==
    ``BASE_CAPTURE``).  Feeding the whole LIVE file to a frozen clock made the
    module a scheduled red: the 2026-08-13 durable checkpoint (e9738279704)
    appended 822 rows stamped 2026-08-11/12, and twenty of the twenty-one cases
    here died at once on ``owner source artifact contains a future availability
    clock`` -- an input the capture had not learned yet at the instant it is
    replayed at.

    A replay of a closed admission is only closed if its INPUT is closed, so read
    the input point-in-time.  The boundary is the engine's own prefix watermark
    rather than a hand-typed row count, which keeps expectation and data one
    vintage by construction; ``test_frozen_owner_prefix_matches_the_reviewed_384_rows``
    is what proves the boundary still names the reviewed bytes.
    """

    lines = SOURCE.read_bytes().splitlines()[: records.ACTIVATION_PREFIX_ROWS]
    return b"".join(line + b"\n" for line in lines)


def _deployed_capture_clock(body: bytes) -> datetime:
    """A capture instant of the SAME vintage as the deployed ledger.

    The deployed capture is gated twice on the clock: no availability stamp may
    lie in its future, and the artifact's newest session must be exactly
    ``nyse_calendar.expected_last_session(captured_at)`` -- which only names a
    session once its 17:00 ET settle buffer has passed.  Wall-clock ``now`` is
    therefore wrong for several hours every night, in the window between that
    settle boundary and the lane's own write, so derive the instant from the
    artifact instead: late on the ledger's OWN newest session.  Both gates are
    asserted rather than assumed, so a calendar or producer change fails loudly
    here instead of silently re-timing the capture.
    """

    rows = [json.loads(line) for line in body.splitlines()]
    latest = max(date.fromisoformat(row["session_date"]) for row in rows)
    settled = datetime.combine(latest, time(23, 0), tzinfo=nyse_calendar.ET).astimezone(
        timezone.utc
    )
    newest_available = max(
        datetime.fromisoformat(row["available_at"].replace("Z", "+00:00"))
        for row in rows
    )
    assert nyse_calendar.expected_last_session(settled) == latest
    assert newest_available <= settled
    return settled


def _base_rows() -> list[dict]:
    return [
        json.loads(line)
        for line in _activation_body().decode("utf-8").splitlines()
    ]


def _future_row() -> dict:
    template = next(
        row for row in _base_rows() if row["contract"]["expiration"] >= "2026-08-11"
    )
    row = copy.deepcopy(template)
    row["source_event_id"] = "market-memory-forward-fixture"
    row["episode_id"] = options_signal_episode._episode_id(
        row["source"], row["source_event_id"]
    )
    row["event_time"] = "2026-08-11T14:08:40Z"
    row["observed_at"] = "2026-08-11T14:08:41Z"
    row["decision_at"] = "2026-08-11T14:08:42Z"
    row["available_at"] = "2026-08-11T14:08:43Z"
    row["published_at"] = None
    row["session_date"] = "2026-08-11"
    row["feature_snapshot"]["dte"] = (
        date.fromisoformat(row["contract"]["expiration"]) - date(2026, 8, 11)
    ).days
    row["provenance"]["source_artifact"] = "live_flow/events/2026-08-11.jsonl"
    row["provenance"]["source_snapshot_asof"] = row["available_at"]
    row["provenance"]["feature_cutoff"] = row["available_at"]
    options_signal_episode.validate_episode(row)
    return row


def _second_future_row() -> dict:
    row = _future_row()
    row["source_event_id"] = "market-memory-forward-fixture-2"
    row["episode_id"] = options_signal_episode._episode_id(
        row["source"], row["source_event_id"]
    )
    row["event_time"] = "2026-08-11T14:09:40Z"
    row["observed_at"] = "2026-08-11T14:09:41Z"
    row["decision_at"] = "2026-08-11T14:09:42Z"
    row["available_at"] = "2026-08-11T14:09:43Z"
    row["provenance"]["source_snapshot_asof"] = row["available_at"]
    row["provenance"]["feature_cutoff"] = row["available_at"]
    options_signal_episode.validate_episode(row)
    return row


def _capture_base(store: Path):
    with _clock(BASE_CAPTURE):
        return records.capture_options_episode_source(
            store,
            source_body=_activation_body(),
            source_commit=COMMIT,
        )


def _capture_forward(store: Path):
    rows = _base_rows() + [_future_row()]
    with _clock(FORWARD_CAPTURE):
        return records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(rows),
            source_commit="b" * 40,
        )


def test_frozen_owner_prefix_matches_the_reviewed_384_rows() -> None:
    # The deployed ledger only ever GROWS -- the reviewed prefix inside it may
    # never move, and a shrinking ledger is a defect rather than weather.  This is
    # the assertion that keeps `_activation_body()`'s point-in-time read honest:
    # everything else in this module trusts the boundary, so the boundary is
    # proven here, literal by literal, against the engine's own watermark.
    live = SOURCE.read_bytes().splitlines()
    assert len(live) >= records.ACTIVATION_PREFIX_ROWS == 384
    body = _activation_body()
    assert len(body.splitlines()) == records.ACTIVATION_PREFIX_ROWS
    assert hashlib.sha256(body).hexdigest() == records.ACTIVATION_PREFIX_SHA256
    assert _base_rows()[-1]["episode_id"] == records.ACTIVATION_LAST_EPISODE_ID
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    provenance = schema["properties"]["provenance"]["properties"]
    assert records.MAX_SOURCE_ROWS == 25_000
    assert records.MAX_SOURCE_BYTES == 48 * 1024 * 1024
    assert provenance["source_row_index"]["maximum"] == records.MAX_SOURCE_ROWS - 1
    assert provenance["source_artifact_bytes"]["maximum"] == records.MAX_SOURCE_BYTES


def test_first_capture_is_real_actual_output_but_never_forward_proof(
    tmp_path: Path,
) -> None:
    stored = _capture_base(_store(tmp_path))

    assert len(stored.generation["records"]) == 384
    assert stored.capture_receipt["era_counts"] == {
        "pre_activation_actual_output": 384,
        "production_forward": 0,
    }
    assert all(
        entry["era"] == "pre_activation_actual_output"
        for entry in stored.generation["records"]
    )
    first = records.load_production_record(
        _store(tmp_path), episode_id=stored.generation["records"][0]["episode_id"]
    )
    assert first["evidence"]["forward_grading_eligible"] is False
    assert first["evidence"]["reconstruction_ingest_supported"] is False
    assert first["temporal"]["known_at"] == "2026-08-11T12:02:48Z"
    assert first["temporal"]["known_at"] != first["temporal"]["source_available_at"]


def test_post_activation_append_is_the_only_forward_era(tmp_path: Path) -> None:
    store = _store(tmp_path)
    initial = _capture_base(store)
    forward = _capture_forward(store)

    assert len(initial.generation["records"]) == 384
    assert len(forward.generation["records"]) == 385
    assert forward.capture_receipt["era_counts"] == {
        "pre_activation_actual_output": 0,
        "production_forward": 1,
    }
    record = records.load_production_record(
        store, episode_id=_future_row()["episode_id"]
    )
    assert record["era"] == "production_forward"
    assert record["evidence"]["forward_grading_eligible"] is True
    assert record["temporal"]["known_at"] == "2026-08-12T12:02:48Z"


def test_exact_duplicate_is_idempotent_and_identity_is_clock_free(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    first = _capture_base(store)
    # By the next completed session, the owner ledger may remain identical
    # because no event qualified. Idempotency must not infer stale vs zero or
    # create a second capture.
    with _clock(datetime(2026, 8, 12, 12, 2, 48, tzinfo=timezone.utc)):
        second = records.capture_options_episode_source(
            store, source_body=_activation_body(), source_commit=COMMIT
        )

    assert second.action == "already_captured_no_new_owner_record"
    assert records.capture_result_payload(second)["freshness_interpretation"] == (
        "unchanged_source_no_zero_event_or_freshness_claim"
    )
    assert len(second.generation["captures"]) == 1
    assert second.generation["generation_id"] == first.generation["generation_id"]
    entry = first.generation["records"][0]
    assert entry["record_id"] == records._record_id(entry["source_record_sha256"])


def test_same_owner_identity_with_conflicting_facts_fails_before_head_moves(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _capture_base(store)
    forward = _capture_forward(store)
    head_before = (store / "HEAD.json").read_bytes()
    rows = _base_rows() + [_future_row()]
    rows[-1]["decision"]["reason"] = "hostile same-id fact drift"
    options_signal_episode.validate_episode(rows[-1])

    with (
        _clock(FORWARD_CAPTURE),
        pytest.raises(
            records.MarketMemoryProductionRecordCaptureError,
            match="mutated or reordered",
        ),
    ):
        records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(rows),
            source_commit="c" * 40,
        )

    assert (store / "HEAD.json").read_bytes() == head_before
    assert len(forward.generation["records"]) == 385


def test_temporal_correction_of_frozen_history_is_refused_without_store_mutation(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _capture_base(store)
    head_before = (store / "HEAD.json").read_bytes()
    rows = _base_rows()
    rows[0]["published_at"] = rows[0]["available_at"]
    options_signal_episode.validate_episode(rows[0])

    with (
        _clock(BASE_CAPTURE),
        pytest.raises(
            records.MarketMemoryProductionRecordCaptureError,
            match="prefix mutated",
        ),
    ):
        records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(rows),
            source_commit="d" * 40,
        )

    assert (store / "HEAD.json").read_bytes() == head_before


def test_authority_smuggling_and_future_clock_are_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _capture_base(store)
    hostile = _future_row()
    hostile["decision"]["authority"]["may_rank"] = True
    with (
        _clock(FORWARD_CAPTURE),
        pytest.raises(records.MarketMemoryProductionRecordCaptureError),
    ):
        records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(_base_rows() + [hostile]),
            source_commit="e" * 40,
        )

    future = _future_row()
    with pytest.raises(
        records.MarketMemoryProductionRecordCaptureError,
        match="future durable availability",
    ):
        records.build_production_record(
            source_record=future,
            source_record_body=records._canonical_bytes(future),
            source_row_index=384,
            source_artifact_sha256="f" * 64,
            source_artifact_bytes=1_000_000,
            source_commit="f" * 40,
            captured_at="2026-08-11T14:08:42.500000Z",
            activated_at="2026-08-11T12:02:48Z",
        )

    head_before = (store / "HEAD.json").read_bytes()
    with (
        _clock(datetime(2026, 8, 11, 14, 8, 42, tzinfo=timezone.utc)),
        pytest.raises(
            records.MarketMemoryProductionRecordCaptureError,
            match="future availability clock",
        ),
    ):
        records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(_base_rows() + [future]),
            source_commit="f" * 40,
        )
    assert (store / "HEAD.json").read_bytes() == head_before


def test_backdated_store_activation_is_impossible() -> None:
    with pytest.raises(
        records.MarketMemoryProductionRecordCaptureError,
        match="cannot predate",
    ):
        records._build_manifest(activated_at="2026-08-11T12:02:47Z")

    manifest = records._build_manifest(activated_at=records.CONTRACT_FROZEN_AT)
    manifest["activated_at"] = "2026-08-11T12:02:47Z"
    manifest["store_id"] = records._content_id(
        "mmprodstore_", manifest, field="store_id"
    )
    with pytest.raises(
        records.MarketMemoryProductionRecordError,
        match="predates",
    ):
        records._validate_manifest(manifest)


def test_new_snapshot_must_match_latest_completed_session(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _capture_base(store)
    head_before = (store / "HEAD.json").read_bytes()

    with (
        _clock(datetime(2026, 8, 13, 12, 2, 48, tzinfo=timezone.utc)),
        pytest.raises(
            records.MarketMemoryProductionRecordCaptureError,
            match="completed-session calendar",
        ),
    ):
        records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(_base_rows() + [_future_row()]),
            source_commit="1" * 40,
        )
    assert (store / "HEAD.json").read_bytes() == head_before


def test_capture_clock_rollback_cannot_reorder_durable_knowledge(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _capture_base(store)
    with _clock(datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc)):
        records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(_base_rows() + [_future_row()]),
            source_commit="2" * 40,
        )
    head_before = (store / "HEAD.json").read_bytes()

    with (
        _clock(datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)),
        pytest.raises(
            records.MarketMemoryProductionRecordCaptureError,
            match="clock rolled back",
        ),
    ):
        records.capture_options_episode_source(
            store,
            source_body=_canonical_jsonl(
                _base_rows() + [_future_row(), _second_future_row()]
            ),
            source_commit="3" * 40,
        )
    assert (store / "HEAD.json").read_bytes() == head_before


def test_missing_values_remain_null_and_carry_explicit_reasons(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stored = _capture_base(store)
    entry = next(
        item
        for item in stored.generation["records"]
        if _base_rows()[item["source_row_index"]]["feature_snapshot"]["vol_gt_prior_oi"]
        is None
    )
    record = records.load_production_record(store, episode_id=entry["episode_id"])

    assert record["facts"]["feature_snapshot"]["vol_gt_prior_oi"] is None
    assert record["temporal"]["published_at"] is None
    assert {item["field"] for item in record["missingness"]} >= {
        "source_record.published_at",
        "source_record.feature_snapshot.vol_gt_prior_oi",
    }


def test_replay_is_exact_no_fallback_and_byte_equivalent_across_generations(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    initial = _capture_base(store)
    episode_id = initial.generation["records"][0]["episode_id"]
    before = records.replay_production_record_as_known_at(
        store,
        episode_id=episode_id,
        as_known_at="2026-08-11T12:02:47Z",
    )
    after_one = records.replay_production_record_as_known_at(
        store,
        episode_id=episode_id,
        as_known_at="2026-08-11T12:02:49Z",
    )
    _capture_forward(store)
    after_two = records.replay_production_record_as_known_at(
        store,
        episode_id=episode_id,
        as_known_at="2026-08-11T12:02:49Z",
    )
    pinned = records.replay_production_record_as_known_at(
        store,
        episode_id=episode_id,
        as_known_at="2026-08-11T12:02:49Z",
        generation_id=initial.generation["generation_id"],
    )

    assert before["status"] == "not_yet_known"
    assert before["record"] is None
    assert before["missingness"] == [
        {
            "field": "record",
            "reason": "record_first_known_after_requested_cutoff",
        }
    ]
    assert after_one["status"] == "available"
    assert records._canonical_bytes(after_one) == records._canonical_bytes(after_two)
    assert records._canonical_bytes(after_one) == records._canonical_bytes(pinned)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda row: row["authority"].__setitem__("may_rank", True),
        lambda row: row.__setitem__("era", "production_forward"),
        lambda row: row["source_identity"].__setitem__(
            "source_record_sha256", "0" * 64
        ),
        lambda row: row["temporal"].__setitem__("known_at", "2026-08-10T00:00:00Z"),
        lambda row: row.__setitem__("missingness", []),
        lambda row: row["grading_ruler"]["readiness_floor"].__setitem__(
            "minimum_matured_records", 0
        ),
    ],
)
def test_mutation_guards_reject_every_load_bearing_rail(
    tmp_path: Path, mutator
) -> None:
    store = _store(tmp_path)
    stored = _capture_base(store)
    record = records.load_production_record(
        store, episode_id=stored.generation["records"][0]["episode_id"]
    )
    mutator(record)

    with pytest.raises(records.MarketMemoryProductionRecordError):
        records.validate_production_record(record)


def test_contract_schema_accepts_every_persisted_record(tmp_path: Path) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    store = _store(tmp_path)
    stored = _capture_base(store)

    records._validate_active_state(
        store, manifest=stored.manifest, generation=stored.generation
    )
    for entry in stored.generation["records"]:
        raw, _ = records._read_json(
            records._record_path(store, entry["record_id"]),
            limit=records._MAX_RECORD_BYTES,
            label="schema test production record",
        )
        record = records.validate_production_record(raw)
        assert list(validator.iter_errors(record)) == []


def test_active_read_requires_receipt_and_source_delta_evidence(tmp_path: Path) -> None:
    store = _store(tmp_path)
    stored = _capture_base(store)
    episode_id = stored.generation["records"][0]["episode_id"]
    receipt_path = records._capture_path(store, stored.capture_receipt["capture_id"])
    receipt_path.unlink()

    with pytest.raises(
        records.MarketMemoryProductionRecordError,
        match="active capture receipt is unavailable",
    ):
        records.load_production_record(store, episode_id=episode_id)

    # A separate store proves byte tampering in the retained append-delta CAS
    # is also detected before replay can claim authenticated source bytes.
    other_store = tmp_path.resolve() / "other" / "production-record-options-episode-v1"
    other = _capture_base(other_store)
    delta_path = other_store / other.capture_receipt["source_delta"]["object_key"]
    delta_body = delta_path.read_bytes()
    delta_path.write_bytes(b"!" + delta_body[1:])
    with pytest.raises(
        records.MarketMemoryProductionRecordError,
        match="append delta authentication drift",
    ):
        records.load_production_record(
            other_store,
            episode_id=other.generation["records"][0]["episode_id"],
        )


def test_published_prepared_history_does_not_fill_pending_backlog(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    stored = _capture_base(store)
    captures = copy.deepcopy(stored.generation["captures"])
    for index in range(records._MAX_PENDING_PREPARED + 1):
        source_sha = hashlib.sha256(f"published-{index}".encode()).hexdigest()
        path = records._prepared_path(store, source_sha)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"historical published object need not be reparsed")
        captures.append({"source_artifact_sha256": source_sha})

    assert (
        records._pending_prepared(
            store,
            manifest=stored.manifest,
            generation={"captures": captures},
        )
        == []
    )


def test_cold_bootstrap_delta_can_exceed_incremental_delta_bound(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    body = b"x" * (records.MAX_SOURCE_DELTA_BYTES + 1)
    snapshot = records.SourceSnapshot(
        body=body,
        sha256=hashlib.sha256(body).hexdigest(),
        source_commit=COMMIT,
        record_count=records.ACTIVATION_PREFIX_ROWS,
        latest_session=date(2026, 8, 10),
        last_available_at=BASE_CAPTURE,
    )
    manifest = records._build_manifest(activated_at=records.CONTRACT_FROZEN_AT)
    generation = records._empty_generation(manifest["store_id"])

    prepared = records._prepare_snapshot(
        store,
        snapshot=snapshot,
        manifest=manifest,
        generation=generation,
        captured_at=records.CONTRACT_FROZEN_AT,
    )

    assert prepared["source_delta"]["bytes"] > records.MAX_SOURCE_DELTA_BYTES
    assert prepared["source_delta"]["bytes"] <= records.MAX_SOURCE_BYTES
    assert records._validate_prepared(prepared, manifest=manifest) == prepared


def test_source_is_read_from_git_and_never_mutated(tmp_path: Path) -> None:
    # The only case here that reads the LIVE deployed ledger rather than the
    # activation prefix, because that is its whole subject: the CLI takes its input
    # from the committed git object and leaves the working tree alone.  Its
    # cardinality is therefore the lane's weather, so it is derived from the very
    # bytes the CLI just read; only the v1 capacity ceilings, which no lane can
    # move, stay literal.
    before = SOURCE.read_bytes()
    committed_rows = len(before.splitlines())
    with _clock(_deployed_capture_clock(before)):
        result = capture_cli.capture_deployed_options_episodes(
            ROOT,
            store_root=_store(tmp_path),
        )

    assert SOURCE.read_bytes() == before
    assert result["source_artifact_sha256"] == hashlib.sha256(before).hexdigest()
    # The floor keeps the derived pair from agreeing with itself about nothing: a
    # capture reporting fewer rows than the reviewed activation prefix is reading
    # something other than the owner ledger.
    assert records.ACTIVATION_PREFIX_ROWS <= committed_rows
    assert result["cumulative_record_count"] == committed_rows
    assert result["v1_capacity"] == {
        "maximum_source_rows": 25_000,
        "maximum_source_bytes": 48 * 1024 * 1024,
        "migration_warning_at_rows": 20_000,
        "remaining_rows": 25_000 - committed_rows,
        "status": "within_measured_v1_bound",
    }


def test_adapter_is_narrow_network_dark_and_has_no_generic_ingest_surface() -> None:
    module = ast.parse(
        (ROOT / "engine/neuralweb/market_memory_production_records.py").read_text(
            encoding="utf-8"
        )
    )
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(module)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imports.isdisjoint(
        {"requests", "httpx", "socket", "openai", "anthropic", "subprocess"}
    )
    assert records.RECORD_CLASS == "options.signal_episode/v1"
    assert not hasattr(records, "ingest_record")
    assert records._AUTHORITY["may_add_candidates"] is False
    assert records._EVIDENCE_POLICY["retrieval_eligible"] is False


def test_grading_ruler_is_future_owner_join_not_an_edge_claim() -> None:
    ruler = records._GRADING_RULER
    assert ruler["cohort_predicate"] == (
        "record.era=production_forward AND "
        "record.evidence.forward_grading_eligible=true"
    )
    assert ruler["numeric_outcome_predicate"] == (
        "owner_outcome.status=complete AND owner_outcome.underlying.status=complete"
    )
    assert ruler["measurements"] == [
        "owner_outcome.underlying.ret",
        "owner_outcome.underlying.mfe",
        "owner_outcome.underlying.mae",
    ]
    assert ruler["correction_policy"] == (
        "owner_v1_immutable_conflict_refusal_"
        "correction_requires_versioned_owner_contract"
    )
    assert ruler["horizons"] == ["h+60", "eod", "1d", "3d", "5d", "10d"]
    assert ruler["option_pnl"] == "unavailable_without_executable_nbbo_evidence"
    assert ruler["readiness_floor"] == {
        "minimum_matured_records": 30,
        "minimum_distinct_session_dates": 20,
        "minimum_distinct_tickers": 20,
        "dependence_cluster": "session_date+ticker",
        "meaning": "evaluation_readiness_only_not_promotion_or_edge_threshold",
    }
    assert ruler["performance_thresholds_frozen"] is False
    assert ruler["training_eligible"] is False
    assert ruler["promotion_eligible"] is False
