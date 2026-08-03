from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import engine.biocatalyst.endpoint_alignment as endpoint_alignment
import engine.sector_intelligence.contracts as sector_contracts
from engine.biocatalyst.endpoint_alignment import (
    EndpointAlignmentError,
    build_trial_endpoint_alignment_review_projection,
)
from engine.biocatalyst.history import build_history_exact_diff
from engine.sector_intelligence import (
    ContractValidationError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
    validate_trial_endpoint_alignment_candidate_against_history,
    validate_trial_endpoint_alignment_review_projection_against_history,
)
from tests.test_biocatalyst_history import NCT_ID, _history_chain, _rehash, _study


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (
        ROOT / "data" / "biocatalyst" / "fixtures" / "endpoint_alignment" / "endpoint_alignment_cases.v1.json"
    ).read_text(encoding="utf-8")
)["cases"]


def _projection(before: dict, after: dict) -> tuple[list[dict], dict, dict]:
    _run, _receipts, snapshots = _history_chain(before, after)
    diff = build_history_exact_diff(
        *snapshots, transaction_from=snapshots[1]["transaction_from"]
    )
    return snapshots, diff, build_trial_endpoint_alignment_review_projection(
        snapshots[0], snapshots[1], diff
    )


def _candidate_projection() -> tuple[list[dict], dict, dict]:
    spelling = FIXTURE["spelling_correction"]
    return _projection(
        _study(outcomes=[spelling["before"]]), _study(outcomes=[spelling["after"]])
    )


def _next_immutable_snapshot(prior: dict, corrected_study: dict) -> dict:
    """A schema-valid synthetic successor for a T2 correction/replay proof.

    T2 accepts prevalidated immutable snapshots; B2 raw-evidence replay remains
    owned by its own tests. This helper models an already-receipted next version
    without mutating the historical source input passed to the projection.
    """

    successor = deepcopy(prior)
    version = prior["source_version"] + 1
    content_hash = canonical_json_sha256(corrected_study)
    successor["source_version"] = version
    successor["display_version"] = version + 1
    successor["canonical_study"] = corrected_study
    successor["canonical_content_sha256"] = content_hash
    successor["source_record_ref"] = (
        f"src:ctgov-history:{NCT_ID}:version:{version}:sha256:{content_hash}"
    )
    successor["source_uri"] = (
        f"https://clinicaltrials.gov/study/{NCT_ID}?a={version + 1}&tab=history"
    )
    seed = canonical_json_sha256(
        {
            "nct_id": NCT_ID,
            "source_version": version,
            "canonical_content_sha256": content_hash,
            "run_ref": successor["run_ref"],
        }
    )
    successor["source_snapshot_id"] = f"ctgov_history_snapshot_{NCT_ID}_{seed[:24]}"
    successor["transaction_from"] = "2026-08-02T00:00:13Z"
    _rehash(successor, "snapshot_payload_sha256")
    return successor


@pytest.mark.parametrize(
    ("before_outcomes", "after_outcomes"),
    [
        (
            [
                {"measure": "Response rate", "timeFrame": "12 weeks", "description": "A"},
                {"measure": "Duration of response", "timeFrame": "24 weeks", "description": "B"},
            ],
            [
                {"measure": "Duration of response", "timeFrame": "24 weeks", "description": "B"},
                {"measure": "Response rate", "timeFrame": "12 weeks", "description": "A"},
            ],
        ),
        (
            [FIXTURE["unicode_whitespace_equivalent"]["before"]],
            [FIXTURE["unicode_whitespace_equivalent"]["after"]],
        ),
    ],
)
def test_reorder_or_unique_nfc_case_whitespace_equivalent_rows_emit_no_candidate(
    before_outcomes: list[dict], after_outcomes: list[dict]
) -> None:
    _snapshots, _diff, projection = _projection(
        _study(outcomes=before_outcomes), _study(outcomes=after_outcomes)
    )

    assert projection["available"] is True
    assert projection["candidate_count"] == 0
    assert projection["candidates"] == []


def test_spelling_correction_is_a2_needs_review_candidate_only() -> None:
    snapshots, diff, projection = _candidate_projection()

    assert projection["available"] is True
    assert projection["candidate_count"] == 1
    candidate = projection["candidates"][0]
    assert candidate["candidate_relation"] == "possible_same_registry_endpoint"
    assert candidate["review_state"] == "needs_review"
    assert candidate["persistence_state"] == "projection_only"
    assert candidate["canonical_queue"] is False
    assert candidate["source_fact"] is False
    assert candidate["protocol_change_asserted"] is False
    assert candidate["materiality_assessed"] is False
    assert candidate["authority"] == {
        "classification": "semantic_candidate",
        "decision_authority": False,
        "maximum_authority": "A2_ATTEND",
        "allowed_uses": ["display", "context", "explain", "attend"],
        "forbidden_uses": [
            "originate_signal",
            "issuer_resolution",
            "security_resolution",
            "rank_security",
            "select_security",
            "size_position",
            "gate_decision",
            "execute_trade",
            "neural_web_authority",
            "all_prophet_uses",
            "raise_authority",
        ],
    }
    assert candidate["before"]["endpoint"]["measure"] == "Tumor response rate"
    assert candidate["after"]["endpoint"]["measure"] == "Tumour response rate"
    assert candidate["supporting_exact_op_sha256"]
    assert candidate["lexical_features"]["measure_similarity_bps"] >= 8000
    validate_trial_endpoint_alignment_candidate_against_history(
        candidate, snapshots[0], snapshots[1], diff
    )


def test_missing_timeframe_and_description_are_zero_not_perfect_corroboration() -> None:
    missing = FIXTURE["missing_corroborating_fields"]
    _snapshots, _diff, projection = _projection(
        _study(outcomes=[missing["before"]]), _study(outcomes=[missing["after"]])
    )

    assert projection["available"] is True
    assert projection["candidate_count"] == 0
    assert projection["candidates"] == []


def test_tied_residuals_emit_every_eligible_cross_pair_in_source_locator_order() -> None:
    snapshots, diff, projection = _projection(
        _study(outcomes=FIXTURE["tied_before"]),
        _study(outcomes=FIXTURE["tied_after"]),
    )

    assert projection["available"] is True
    assert projection["candidate_count"] == 4
    assert [
        (candidate["before"]["outcome_index"], candidate["after"]["outcome_index"])
        for candidate in projection["candidates"]
    ] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert "ranking" not in canonical_json_bytes(projection).decode("utf-8").casefold()
    validate_trial_endpoint_alignment_review_projection_against_history(
        projection, snapshots[0], snapshots[1], diff
    )


def test_replay_rejects_mutation_rehash_wrong_identity_nonadjacency_missing_op_and_unsupported_path() -> None:
    snapshots, diff, projection = _candidate_projection()
    candidate = projection["candidates"][0]

    fabricated = deepcopy(candidate)
    fabricated["before"]["endpoint"]["measure"] = "Fabricated endpoint"
    fabricated["before"]["endpoint_sha256"] = canonical_json_sha256(
        fabricated["before"]["endpoint"]
    )
    _rehash(fabricated, "candidate_payload_sha256")
    with pytest.raises(ContractValidationError):
        validate_trial_endpoint_alignment_candidate_against_history(
            fabricated, snapshots[0], snapshots[1], diff
        )

    wrong_nct = deepcopy(candidate)
    wrong_nct["nct_id"] = "NCT99999999"
    _rehash(wrong_nct, "candidate_payload_sha256")
    with pytest.raises(ContractValidationError):
        validate_trial_endpoint_alignment_candidate_against_history(
            wrong_nct, snapshots[0], snapshots[1], diff
        )

    unsupported_path = deepcopy(candidate)
    unsupported_path["before"]["list_locator"] = "/protocolSection/outcomesModule/unsupported"
    _rehash(unsupported_path, "candidate_payload_sha256")
    with pytest.raises(ContractValidationError):
        validate_contract(unsupported_path)

    missing_operation = deepcopy(diff)
    missing_operation["operations"] = []
    _rehash(missing_operation, "diff_payload_sha256")
    with pytest.raises(ContractValidationError):
        build_trial_endpoint_alignment_review_projection(
            snapshots[0], snapshots[1], missing_operation
        )

    nonadjacent = deepcopy(snapshots[1])
    nonadjacent["source_version"] = 2
    nonadjacent["display_version"] = 3
    nonadjacent["source_record_ref"] = (
        f"src:ctgov-history:{NCT_ID}:version:2:sha256:{nonadjacent['canonical_content_sha256']}"
    )
    nonadjacent["source_uri"] = f"https://clinicaltrials.gov/study/{NCT_ID}?a=3&tab=history"
    seed = canonical_json_sha256(
        {
            "nct_id": NCT_ID,
            "source_version": 2,
            "canonical_content_sha256": nonadjacent["canonical_content_sha256"],
            "run_ref": nonadjacent["run_ref"],
        }
    )
    nonadjacent["source_snapshot_id"] = f"ctgov_history_snapshot_{NCT_ID}_{seed[:24]}"
    _rehash(nonadjacent, "snapshot_payload_sha256")
    with pytest.raises(ContractValidationError):
        build_trial_endpoint_alignment_review_projection(snapshots[0], nonadjacent, diff)


def test_inputs_stay_immutable_and_identical_replay_is_byte_identical() -> None:
    spelling = FIXTURE["spelling_correction"]
    _run, _receipts, snapshots = _history_chain(
        _study(outcomes=[spelling["before"]]), _study(outcomes=[spelling["after"]])
    )
    diff = build_history_exact_diff(
        *snapshots, transaction_from=snapshots[1]["transaction_from"]
    )
    originals = deepcopy((snapshots, diff))

    first = build_trial_endpoint_alignment_review_projection(snapshots[0], snapshots[1], diff)
    second = build_trial_endpoint_alignment_review_projection(snapshots[0], snapshots[1], diff)

    assert (snapshots, diff) == originals
    assert first == second
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_closed_schemas_forbid_decisions_identity_prophet_raw_store_and_extra_properties() -> None:
    _snapshots, _diff, projection = _candidate_projection()
    candidate = projection["candidates"][0]

    for state in ("accepted", "rejected"):
        altered = deepcopy(candidate)
        altered["review_state"] = state
        _rehash(altered, "candidate_payload_sha256")
        with pytest.raises(ContractValidationError):
            validate_contract(altered)

    for forbidden in (
        "issuer",
        "ticker",
        "security",
        "ranking",
        "Prophet",
        "raw_store",
        "extra_property",
    ):
        altered = deepcopy(candidate)
        altered[forbidden] = "forbidden"
        with pytest.raises(ContractValidationError):
            validate_contract(altered)

    projection_extra = deepcopy(projection)
    projection_extra["canonical_review_queue"] = True
    with pytest.raises(ContractValidationError):
        validate_contract(projection_extra)

    for field in ("persistence_state", "canonical_queue"):
        altered = deepcopy(candidate)
        altered.pop(field)
        _rehash(altered, "candidate_payload_sha256")
        with pytest.raises(ContractValidationError):
            validate_contract(altered)

    canonical_candidate = deepcopy(candidate)
    canonical_candidate["persistence_state"] = "canonical"
    canonical_candidate["canonical_queue"] = True
    _rehash(canonical_candidate, "candidate_payload_sha256")
    with pytest.raises(ContractValidationError):
        validate_contract(canonical_candidate)

    candidate_schema = json.loads(
        (
            ROOT
            / "contracts"
            / "biocatalyst"
            / "trial_endpoint_alignment_candidate.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert candidate_schema["properties"]["persistence_state"] == {
        "const": "projection_only"
    }
    assert candidate_schema["properties"]["canonical_queue"] == {"const": False}
    assert {"persistence_state", "canonical_queue"}.issubset(candidate_schema["required"])


@pytest.mark.parametrize(
    ("corruption", "expected_path", "expected_code"),
    [
        (
            "candidate_payload_sha256",
            "$.candidates[0].candidate_payload_sha256",
            "endpoint_alignment_candidate.hash",
        ),
        (
            "endpoint_sha256",
            "$.candidates[0].before.endpoint_sha256",
            "endpoint_alignment_candidate.endpoint_hash",
        ),
    ],
)
def test_generic_projection_validation_applies_embedded_candidate_semantics(
    corruption: str, expected_path: str, expected_code: str
) -> None:
    _snapshots, _diff, projection = _candidate_projection()
    if corruption == "candidate_payload_sha256":
        projection["candidates"][0]["candidate_payload_sha256"] = "0" * 64
    else:
        projection["candidates"][0]["before"]["endpoint_sha256"] = "0" * 64
    _rehash(projection, "projection_payload_sha256")

    with pytest.raises(ContractValidationError) as exc_info:
        validate_contract(projection)

    assert (expected_path, expected_code) in {
        (issue.path, issue.code) for issue in exc_info.value.issues
    }
    assert not any(
        issue.code == "endpoint_alignment_projection.hash"
        for issue in exc_info.value.issues
    )


@pytest.mark.parametrize("artifact_kind", ["candidate", "projection"])
def test_generic_validation_deep_artifact_is_a_deterministic_contract_error(
    artifact_kind: str,
) -> None:
    _snapshots, _diff, projection = _candidate_projection()
    artifact = (
        projection["candidates"][0] if artifact_kind == "candidate" else projection
    )
    embedded_candidate = (
        artifact if artifact_kind == "candidate" else artifact["candidates"][0]
    )
    nested: object = "leaf"
    for _ in range(2_000):
        nested = [nested]
    embedded_candidate["before"]["endpoint"]["hostile_nested_value"] = nested

    observed_issues: list[tuple] = []
    for _ in range(2):
        with pytest.raises(ContractValidationError) as exc_info:
            validate_contract(artifact)
        observed_issues.append(exc_info.value.issues)

    assert observed_issues[0] == observed_issues[1]
    assert [(issue.path, issue.code) for issue in observed_issues[0]] == [
        ("$", "schema.invalid_in_memory_document")
    ]


@pytest.mark.parametrize(
    ("artifact_kind", "padding_size", "expected_path", "expected_code"),
    [
        (
            "candidate",
            1024 * 1024,
            "$",
            "endpoint_alignment_candidate.byte_limit",
        ),
        (
            "projection",
            1024 * 1024,
            "$",
            "endpoint_alignment_projection.byte_limit",
        ),
        (
            "projection",
            50_000,
            "$.candidates[0]",
            "endpoint_alignment_candidate.byte_limit",
        ),
    ],
)
def test_generic_over_cap_artifact_refuses_before_canonicalization_or_hashing(
    monkeypatch: pytest.MonkeyPatch,
    artifact_kind: str,
    padding_size: int,
    expected_path: str,
    expected_code: str,
) -> None:
    _snapshots, _diff, projection = _candidate_projection()
    artifact = (
        projection["candidates"][0] if artifact_kind == "candidate" else projection
    )
    embedded_candidate = (
        artifact if artifact_kind == "candidate" else artifact["candidates"][0]
    )
    embedded_candidate["before"]["endpoint"]["hostile_padding"] = "x" * padding_size
    reached = {"canonical": 0, "hash": 0, "identity": 0}

    def forbidden(stage: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            reached[stage] += 1
            raise AssertionError(f"generic over-cap artifact reached {stage}")

        return fail

    monkeypatch.setattr(
        sector_contracts, "canonical_json_bytes", forbidden("canonical")
    )
    monkeypatch.setattr(
        sector_contracts, "canonical_json_sha256", forbidden("hash")
    )
    monkeypatch.setattr(
        sector_contracts,
        (
            "_endpoint_alignment_candidate_identity"
            if artifact_kind == "candidate"
            else "_endpoint_alignment_projection_identity"
        ),
        forbidden("identity"),
    )

    with pytest.raises(ContractValidationError) as exc_info:
        validate_contract(artifact)

    assert (expected_path, expected_code) in {
        (issue.path, issue.code) for issue in exc_info.value.issues
    }
    assert reached == {"canonical": 0, "hash": 0, "identity": 0}


def test_generic_bounded_refusal_is_independent_of_mapping_insertion_order() -> None:
    invalid_key = "\ud800"
    oversized_key = "a" * (endpoint_alignment._MAX_CANDIDATE_BYTES + 1)
    observed_issues: list[tuple] = []

    for endpoint_items in (
        ((invalid_key, None), (oversized_key, None)),
        ((oversized_key, None), (invalid_key, None)),
    ):
        _snapshots, _diff, projection = _candidate_projection()
        projection["candidates"][0]["before"]["endpoint"] = dict(endpoint_items)
        with pytest.raises(ContractValidationError) as exc_info:
            validate_contract(projection["candidates"][0])
        observed_issues.append(exc_info.value.issues)

    assert observed_issues[0] == observed_issues[1]
    assert [(issue.path, issue.code) for issue in observed_issues[0]] == [
        ("$", "endpoint_alignment_candidate.byte_limit")
    ]


@pytest.mark.parametrize(
    ("artifact_kind", "limit"),
    [
        ("candidate", endpoint_alignment._MAX_CANDIDATE_BYTES),
        ("projection", endpoint_alignment._MAX_PROJECTION_BYTES),
    ],
)
def test_artifact_preflight_canonical_byte_caps_are_exact(
    artifact_kind: str, limit: int
) -> None:
    preflight = (
        endpoint_alignment._preflight_candidate
        if artifact_kind == "candidate"
        else endpoint_alignment._preflight_projection
    )
    empty_size = len(canonical_json_bytes({"padding": ""}))
    exact = {"padding": "x" * (limit - empty_size)}
    one_over = {"padding": exact["padding"] + "x"}

    frozen = preflight(exact)
    generic_size, generic_reason = sector_contracts._bounded_canonical_json_size(
        exact, limit=limit
    )
    over_size, over_reason = sector_contracts._bounded_canonical_json_size(
        one_over, limit=limit
    )

    assert len(canonical_json_bytes(frozen)) == limit
    assert (generic_size, generic_reason) == (limit, None)
    assert (over_size, over_reason) == (None, "limit")
    with pytest.raises(
        EndpointAlignmentError,
        match=rf"^endpoint_alignment_{artifact_kind}_canonical_byte_limit_exceeded$",
    ):
        preflight(one_over)


@pytest.mark.parametrize(
    ("target_index", "target_label"),
    [(0, "before_snapshot"), (1, "after_snapshot"), (2, "diff")],
)
def test_complete_history_input_byte_preflight_refuses_before_copy_replay_or_candidate(
    monkeypatch: pytest.MonkeyPatch, target_index: int, target_label: str
) -> None:
    snapshots, diff, _projection_document = _candidate_projection()
    inputs = [deepcopy(snapshots[0]), deepcopy(snapshots[1]), deepcopy(diff)]
    hostile_value = "x" * (2 * 1024 * 1024 + 1)
    if target_index < 2:
        inputs[target_index]["canonical_study"]["hostileUnrelatedModule"] = hostile_value
    else:
        inputs[target_index]["hostile_unrelated_field"] = hostile_value
    reached = {"copy": 0, "replay": 0, "candidate": 0}

    def forbidden(stage: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            reached[stage] += 1
            raise AssertionError(f"{stage} must not run before full-input preflight")

        return fail

    monkeypatch.setattr(endpoint_alignment, "_json_copy", forbidden("copy"))
    monkeypatch.setattr(
        endpoint_alignment,
        "validate_trial_history_diff_against_snapshots",
        forbidden("replay"),
    )
    monkeypatch.setattr(endpoint_alignment, "_make_candidate", forbidden("candidate"))

    artifact = None
    with pytest.raises(
        EndpointAlignmentError,
        match=rf"^endpoint_alignment_{target_label}_canonical_byte_limit_exceeded$",
    ):
        artifact = build_trial_endpoint_alignment_review_projection(*inputs)

    assert artifact is None
    assert reached == {"copy": 0, "replay": 0, "candidate": 0}


@pytest.mark.parametrize(
    ("hostile_value", "reason"),
    [
        (list(range(16_385)), "container_limit_exceeded"),
        ([[None] * 700 for _ in range(100)], "node_limit_exceeded"),
    ],
)
def test_complete_history_input_container_and_node_preflight_refuse_without_artifact(
    monkeypatch: pytest.MonkeyPatch, hostile_value: object, reason: str
) -> None:
    snapshots, diff, _projection_document = _candidate_projection()
    before = deepcopy(snapshots[0])
    before["canonical_study"]["hostile_unrelated_module"] = hostile_value
    reached = {"copy": 0, "replay": 0}

    def forbidden(stage: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            reached[stage] += 1
            raise AssertionError(f"{stage} must not run before full-input preflight")

        return fail

    monkeypatch.setattr(endpoint_alignment, "_json_copy", forbidden("copy"))
    monkeypatch.setattr(
        endpoint_alignment,
        "validate_trial_history_diff_against_snapshots",
        forbidden("replay"),
    )

    artifact = None
    with pytest.raises(
        EndpointAlignmentError,
        match=rf"^endpoint_alignment_before_snapshot_{reason}$",
    ):
        artifact = build_trial_endpoint_alignment_review_projection(before, snapshots[1], diff)

    assert artifact is None
    assert reached == {"copy": 0, "replay": 0}


def test_complete_history_input_depth_preflight_is_iterative_and_refuses_without_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots, diff, _projection_document = _candidate_projection()
    before = deepcopy(snapshots[0])
    nested: object = "leaf"
    for _ in range(129):
        nested = [nested]
    before["canonical_study"]["hostile_unrelated_module"] = nested
    reached = {"copy": 0, "replay": 0}

    def forbidden(stage: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            reached[stage] += 1
            raise AssertionError(f"{stage} must not run before full-input preflight")

        return fail

    monkeypatch.setattr(endpoint_alignment, "_json_copy", forbidden("copy"))
    monkeypatch.setattr(
        endpoint_alignment,
        "validate_trial_history_diff_against_snapshots",
        forbidden("replay"),
    )

    artifact = None
    with pytest.raises(
        EndpointAlignmentError,
        match=r"^endpoint_alignment_before_snapshot_nesting_limit_exceeded$",
    ):
        artifact = build_trial_endpoint_alignment_review_projection(before, snapshots[1], diff)

    assert artifact is None
    assert reached == {"copy": 0, "replay": 0}


def test_full_input_refusal_reason_is_independent_of_object_insertion_order() -> None:
    snapshots, diff, _projection_document = _candidate_projection()
    oversized = "x" * (2 * 1024 * 1024 + 1)
    too_deep: object = "leaf"
    for _ in range(129):
        too_deep = [too_deep]

    errors: list[str] = []
    for ordered_items in (
        (("a_oversized", oversized), ("z_too_deep", too_deep)),
        (("z_too_deep", too_deep), ("a_oversized", oversized)),
    ):
        before = deepcopy(snapshots[0])
        before["canonical_study"]["hostileUnrelatedModule"] = dict(ordered_items)
        with pytest.raises(EndpointAlignmentError) as exc_info:
            build_trial_endpoint_alignment_review_projection(before, snapshots[1], diff)
        errors.append(str(exc_info.value))

    assert errors == [
        "endpoint_alignment_before_snapshot_canonical_byte_limit_exceeded",
        "endpoint_alignment_before_snapshot_canonical_byte_limit_exceeded",
    ]


@pytest.mark.parametrize("validator_kind", ["candidate", "projection"])
def test_replay_validators_preflight_and_freeze_complete_inputs_before_exact_replay(
    monkeypatch: pytest.MonkeyPatch, validator_kind: str
) -> None:
    snapshots, diff, projection = _candidate_projection()
    before = deepcopy(snapshots[0])
    before["canonical_study"]["hostileUnrelatedModule"] = list(range(16_385))
    replay_calls = 0

    def forbidden_replay(*_args: object, **_kwargs: object) -> None:
        nonlocal replay_calls
        replay_calls += 1
        raise AssertionError("exact replay must not run before full-input preflight")

    monkeypatch.setattr(
        endpoint_alignment,
        "validate_trial_history_diff_against_snapshots",
        forbidden_replay,
    )
    validator = (
        validate_trial_endpoint_alignment_candidate_against_history
        if validator_kind == "candidate"
        else validate_trial_endpoint_alignment_review_projection_against_history
    )
    artifact = projection["candidates"][0] if validator_kind == "candidate" else projection

    with pytest.raises(
        EndpointAlignmentError,
        match=r"^endpoint_alignment_before_snapshot_container_limit_exceeded$",
    ):
        validator(artifact, before, snapshots[1], diff)

    assert replay_calls == 0


@pytest.mark.parametrize(
    ("validator_kind", "artifact_label"),
    [("candidate", "candidate"), ("projection", "projection")],
)
def test_replay_validator_artifact_depth_preflight_is_iterative_and_deterministic(
    validator_kind: str, artifact_label: str
) -> None:
    snapshots, diff, projection = _candidate_projection()
    artifact = (
        projection["candidates"][0] if validator_kind == "candidate" else projection
    )
    embedded_candidate = (
        artifact if validator_kind == "candidate" else artifact["candidates"][0]
    )
    nested: object = "leaf"
    for _ in range(1_200):
        nested = [nested]
    embedded_candidate["before"]["endpoint"]["hostile_nested_value"] = nested
    validator = (
        validate_trial_endpoint_alignment_candidate_against_history
        if validator_kind == "candidate"
        else validate_trial_endpoint_alignment_review_projection_against_history
    )

    with pytest.raises(
        EndpointAlignmentError,
        match=rf"^endpoint_alignment_{artifact_label}_nesting_limit_exceeded$",
    ):
        validator(artifact, snapshots[0], snapshots[1], diff)


@pytest.mark.parametrize(
    ("validator_kind", "artifact_label"),
    [("candidate", "candidate"), ("projection", "projection")],
)
def test_replay_validator_oversized_artifact_refuses_before_any_canonicalization(
    monkeypatch: pytest.MonkeyPatch, validator_kind: str, artifact_label: str
) -> None:
    snapshots, diff, projection = _candidate_projection()
    artifact = (
        projection["candidates"][0] if validator_kind == "candidate" else projection
    )
    embedded_candidate = (
        artifact if validator_kind == "candidate" else artifact["candidates"][0]
    )
    embedded_candidate["before"]["endpoint"]["hostile_padding"] = "x" * (1024 * 1024)
    canonicalization_calls = 0

    def forbidden_canonicalization(_value: object) -> bytes:
        nonlocal canonicalization_calls
        canonicalization_calls += 1
        raise AssertionError("artifact preflight must run before canonicalization")

    monkeypatch.setattr(
        endpoint_alignment, "canonical_json_bytes", forbidden_canonicalization
    )
    monkeypatch.setattr(
        sector_contracts, "canonical_json_bytes", forbidden_canonicalization
    )
    validator = (
        validate_trial_endpoint_alignment_candidate_against_history
        if validator_kind == "candidate"
        else validate_trial_endpoint_alignment_review_projection_against_history
    )

    with pytest.raises(
        EndpointAlignmentError,
        match=rf"^endpoint_alignment_{artifact_label}_canonical_byte_limit_exceeded$",
    ):
        validator(artifact, snapshots[0], snapshots[1], diff)

    assert canonicalization_calls == 0


@pytest.mark.parametrize(
    "reason",
    [
        "canonical_byte_limit_exceeded",
        "container_limit_exceeded",
        "node_limit_exceeded",
        "nesting_limit_exceeded",
    ],
)
def test_projection_validator_preflights_each_embedded_candidate_envelope_first(
    monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    snapshots, diff, projection = _candidate_projection()
    endpoint = projection["candidates"][0]["before"]["endpoint"]
    if reason == "canonical_byte_limit_exceeded":
        endpoint["hostile_value"] = "x" * 50_000
    elif reason == "container_limit_exceeded":
        endpoint["hostile_value"] = [None] * 2_049
    elif reason == "node_limit_exceeded":
        endpoint["hostile_value"] = [[None] * 2_048, [None] * 2_048]
    else:
        nested: object = "leaf"
        for _ in range(100):
            nested = [nested]
        endpoint["hostile_value"] = nested
    reached = {"canonical": 0, "replay": 0, "schema": 0}

    def forbidden(stage: str):
        def fail(*_args: object, **_kwargs: object) -> None:
            reached[stage] += 1
            raise AssertionError(
                f"{stage} must not run before embedded-candidate preflight"
            )

        return fail

    monkeypatch.setattr(
        endpoint_alignment, "canonical_json_bytes", forbidden("canonical")
    )
    monkeypatch.setattr(
        sector_contracts, "canonical_json_bytes", forbidden("canonical")
    )
    monkeypatch.setattr(
        endpoint_alignment,
        "validate_trial_history_diff_against_snapshots",
        forbidden("replay"),
    )
    monkeypatch.setattr(
        endpoint_alignment.ContractRegistry, "validate", forbidden("schema")
    )

    with pytest.raises(
        EndpointAlignmentError,
        match=rf"^endpoint_alignment_projection_candidate_0_{reason}$",
    ):
        validate_trial_endpoint_alignment_review_projection_against_history(
            projection, snapshots[0], snapshots[1], diff
        )

    assert reached == {"canonical": 0, "replay": 0, "schema": 0}


@pytest.mark.parametrize("validator_kind", ["candidate", "projection"])
def test_replay_validator_uses_one_frozen_artifact_when_caller_mutates(
    monkeypatch: pytest.MonkeyPatch, validator_kind: str
) -> None:
    snapshots, diff, projection = _candidate_projection()
    artifact = (
        projection["candidates"][0] if validator_kind == "candidate" else projection
    )
    target_contract = (
        "trial_endpoint_alignment_candidate.v1"
        if validator_kind == "candidate"
        else "trial_endpoint_alignment_review_projection.v1"
    )
    original_validate = endpoint_alignment.ContractRegistry.validate
    frozen_documents: list[dict] = []

    def validate_after_caller_mutation(
        registry: endpoint_alignment.ContractRegistry,
        contract_id: str,
        document: object,
    ) -> None:
        if contract_id == target_contract:
            assert isinstance(document, dict)
            assert document is not artifact
            frozen_documents.append(document)
            if validator_kind == "candidate":
                artifact["canonical_queue"] = True
            else:
                artifact["candidate_count"] = 0
        original_validate(registry, contract_id, document)

    monkeypatch.setattr(
        endpoint_alignment.ContractRegistry, "validate", validate_after_caller_mutation
    )
    validator = (
        validate_trial_endpoint_alignment_candidate_against_history
        if validator_kind == "candidate"
        else validate_trial_endpoint_alignment_review_projection_against_history
    )

    validator(artifact, snapshots[0], snapshots[1], diff)

    assert len(frozen_documents) == 1
    if validator_kind == "candidate":
        assert artifact["canonical_queue"] is True
        assert frozen_documents[0]["canonical_queue"] is False
    else:
        assert artifact["candidate_count"] == 0
        assert frozen_documents[0]["candidate_count"] == 1


def test_input_text_and_residual_capacity_breaches_are_explicit_and_fail_empty() -> None:
    oversized = "x" * (16 * 1024 + 1)
    _snapshots, _diff, text_limited = _projection(
        _study(outcomes=[{"measure": oversized, "timeFrame": "12 weeks", "description": "A"}]),
        _study(outcomes=[{"measure": oversized + " corrected", "timeFrame": "12 weeks", "description": "A"}]),
    )
    assert text_limited["available"] is False
    assert text_limited["unavailable_reason"] == "endpoint_text_limit_exceeded"
    assert text_limited["candidate_count"] == 0
    assert text_limited["candidates"] == []

    byte_wide_before = {
        "measure": "Tumor response rate",
        "timeFrame": "12 weeks",
        "description": "A",
        "note_one": "x" * 12500,
        "note_two": "y" * 12500,
    }
    byte_wide_after = {**byte_wide_before, "measure": "Tumour response rate"}
    _snapshots, _diff, byte_limited = _projection(
        _study(outcomes=[byte_wide_before]), _study(outcomes=[byte_wide_after])
    )
    assert byte_limited["available"] is False
    assert byte_limited["unavailable_reason"] == "endpoint_byte_limit_exceeded"
    assert byte_limited["candidate_count"] == 0

    complexity_before = {
        "measure": "Tumor response rate",
        "timeFrame": "12 weeks",
        "description": "A",
        **{f"field_{index}": "x" for index in range(512)},
    }
    complexity_after = {**complexity_before, "measure": "Tumour response rate"}
    _snapshots, _diff, complexity_limited = _projection(
        _study(outcomes=[complexity_before]), _study(outcomes=[complexity_after])
    )
    assert complexity_limited["available"] is False
    assert complexity_limited["unavailable_reason"] == "endpoint_complexity_limit_exceeded"
    assert complexity_limited["candidate_count"] == 0

    nested_list_before = {
        "measure": "Tumor response rate",
        "timeFrame": "12 weeks",
        "description": "A",
        "nested": ["x"] * 1024,
    }
    nested_list_after = {**nested_list_before, "measure": "Tumour response rate"}
    _snapshots, _diff, nested_list_limited = _projection(
        _study(outcomes=[nested_list_before]), _study(outcomes=[nested_list_after])
    )
    assert nested_list_limited["available"] is False
    assert nested_list_limited["unavailable_reason"] == "endpoint_complexity_limit_exceeded"
    assert nested_list_limited["candidate_count"] == 0

    nested_value: object = "x"
    for _ in range(65):
        nested_value = [nested_value]
    nested_depth_before = {
        "measure": "Tumor response rate",
        "timeFrame": "12 weeks",
        "description": "A",
        "nested": nested_value,
    }
    nested_depth_after = {**nested_depth_before, "measure": "Tumour response rate"}
    _snapshots, _diff, nested_depth_limited = _projection(
        _study(outcomes=[nested_depth_before]), _study(outcomes=[nested_depth_after])
    )
    assert nested_depth_limited["available"] is False
    assert nested_depth_limited["unavailable_reason"] == "endpoint_nesting_limit_exceeded"
    assert nested_depth_limited["candidate_count"] == 0

    residual_before = [
        {"measure": f"Response rate before {index}", "timeFrame": "12 weeks", "description": "A"}
        for index in range(65)
    ]
    residual_after = [
        {"measure": f"Response rate after {index}", "timeFrame": "12 weeks", "description": "A"}
        for index in range(65)
    ]
    _snapshots, _diff, residual_limited = _projection(
        _study(outcomes=residual_before), _study(outcomes=residual_after)
    )
    assert residual_limited["available"] is False
    assert residual_limited["unavailable_reason"] == "residual_before_limit_exceeded"
    assert residual_limited["candidate_count"] == 0
    assert residual_limited["candidates"] == []

    raw_before = [
        {"measure": f"Response rate {index}", "timeFrame": "12 weeks", "description": "A"}
        for index in range(257)
    ]
    raw_after = [
        {"measure": f"Response rates {index}", "timeFrame": "12 weeks", "description": "A"}
        for index in range(257)
    ]
    _snapshots, _diff, source_limited = _projection(
        _study(outcomes=raw_before), _study(outcomes=raw_after)
    )
    assert source_limited["available"] is False
    assert source_limited["unavailable_reason"] == "source_before_row_limit_exceeded"
    assert source_limited["capacity"]["source_before_count"] == 257
    assert source_limited["candidate_count"] == 0
    assert source_limited["candidates"] == []


def test_endpoint_byte_cap_matches_exact_canonical_size_for_reviewer_shaped_mapping() -> None:
    def reviewer_endpoint(target_size: int) -> dict:
        endpoint = {
            "measure": "Tumor response rate",
            "timeFrame": "12 weeks",
            "description": "Independent central review",
            "reviewer_flags": [True, False, None],
            "reviewer_note": "line one\nline two\t\"quoted\"\\path",
            "reviewer_ratio": 1.25,
            **{
                f"reviewer_field_{index:03d}": "x" * 180
                for index in range(100)
            },
            "padding": "",
        }
        remaining = target_size - len(canonical_json_bytes(endpoint))
        assert 0 < remaining < endpoint_alignment._MAX_ENDPOINT_TEXT_BYTES
        endpoint["padding"] = "p" * remaining
        assert len(canonical_json_bytes(endpoint)) == target_size
        return endpoint

    exact = reviewer_endpoint(endpoint_alignment._MAX_ENDPOINT_BYTES)
    one_over = deepcopy(exact)
    one_over["padding"] += "p"
    exact_reversed = dict(reversed(tuple(exact.items())))
    one_over_reversed = dict(reversed(tuple(one_over.items())))

    assert len(canonical_json_bytes(one_over)) == endpoint_alignment._MAX_ENDPOINT_BYTES + 1
    assert endpoint_alignment._endpoint_input_limit_reason(exact) is None
    assert endpoint_alignment._endpoint_input_limit_reason(exact_reversed) is None
    assert (
        endpoint_alignment._endpoint_input_limit_reason(one_over)
        == "endpoint_byte_limit_exceeded"
    )
    assert (
        endpoint_alignment._endpoint_input_limit_reason(one_over_reversed)
        == "endpoint_byte_limit_exceeded"
    )

    eligible_after = {
        "measure": "Tumour response rate",
        "timeFrame": "12 weeks",
        "description": "Independent central review",
    }
    _snapshots, _diff, accepted = _projection(
        _study(outcomes=[exact]), _study(outcomes=[eligible_after])
    )
    _snapshots, _diff, refused = _projection(
        _study(outcomes=[one_over]), _study(outcomes=[eligible_after])
    )

    assert accepted["available"] is True
    assert accepted["candidate_count"] == 1
    assert refused["available"] is False
    assert refused["unavailable_reason"] == "endpoint_byte_limit_exceeded"
    assert refused["candidate_count"] == 0
    assert refused["candidates"] == []


def test_more_than_64_eligible_pairs_short_circuits_to_a_fixed_empty_unavailable_state() -> None:
    before = [
        {"measure": f"Tumor response rate A{index}", "timeFrame": "12 weeks", "description": "A"}
        for index in range(9)
    ]
    after = [
        {"measure": f"Tumour response rate B{index}", "timeFrame": "12 weeks", "description": "A"}
        for index in range(8)
    ]
    _snapshots, _diff, projection = _projection(_study(outcomes=before), _study(outcomes=after))

    assert projection["available"] is False
    assert projection["unavailable_reason"] == "candidate_limit_exceeded"
    assert projection["capacity"]["comparison_count"] == 72
    assert projection["candidate_count"] == 0
    assert projection["candidates"] == []


def test_candidate_and_projection_byte_caps_fail_empty_without_truncating() -> None:
    candidate_wide_before = {
        "measure": "Tumor response rate",
        "timeFrame": "12 weeks",
        "description": "A",
        "note_one": "x" * 11800,
        "note_two": "y" * 11800,
    }
    candidate_wide_after = {
        **candidate_wide_before,
        "measure": "Tumour response rate",
    }
    _snapshots, _diff, candidate_limited = _projection(
        _study(outcomes=[candidate_wide_before]), _study(outcomes=[candidate_wide_after])
    )
    assert candidate_limited["available"] is False
    assert candidate_limited["unavailable_reason"] == "candidate_byte_limit_exceeded"
    assert candidate_limited["candidate_count"] == 0
    assert candidate_limited["candidates"] == []

    projection_before = [
        {
            "measure": f"Tumor response rate A{index}",
            "timeFrame": "12 weeks",
            "description": "A",
            "note": "x" * 3500,
        }
        for index in range(8)
    ]
    projection_after = [
        {
            "measure": f"Tumour response rate B{index}",
            "timeFrame": "12 weeks",
            "description": "A",
            "note": "x" * 3500,
        }
        for index in range(8)
    ]
    _snapshots, _diff, projection_limited = _projection(
        _study(outcomes=projection_before), _study(outcomes=projection_after)
    )
    assert projection_limited["available"] is False
    assert projection_limited["unavailable_reason"] == "projection_byte_limit_exceeded"
    assert projection_limited["candidate_count"] == 0
    assert projection_limited["candidates"] == []


def test_candidate_builder_preflights_before_candidate_identity_or_payload_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_wide_before = {
        "measure": "Tumor response rate",
        "timeFrame": "12 weeks",
        "description": "A",
        "note_one": "x" * 11_800,
        "note_two": "y" * 11_800,
    }
    candidate_wide_after = {
        **candidate_wide_before,
        "measure": "Tumour response rate",
    }
    original_with_hash = endpoint_alignment._with_hash

    def forbidden_candidate_identity(_payload: object) -> None:
        raise AssertionError("over-cap candidate identity must not be hashed")

    def guarded_with_hash(payload: object, field: str) -> dict:
        if field == "candidate_payload_sha256":
            raise AssertionError("over-cap candidate payload must not be canonicalized or hashed")
        return original_with_hash(payload, field)

    monkeypatch.setattr(
        endpoint_alignment, "_candidate_identity", forbidden_candidate_identity
    )
    monkeypatch.setattr(endpoint_alignment, "_with_hash", guarded_with_hash)

    _snapshots, _diff, projection = _projection(
        _study(outcomes=[candidate_wide_before]),
        _study(outcomes=[candidate_wide_after]),
    )

    assert projection["available"] is False
    assert projection["unavailable_reason"] == "candidate_byte_limit_exceeded"
    assert projection["candidate_count"] == 0
    assert projection["candidates"] == []


def test_projection_builder_preflights_before_projection_identity_or_payload_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection_before = [
        {
            "measure": f"Tumor response rate A{index}",
            "timeFrame": "12 weeks",
            "description": "A",
            "note": "x" * 3_500,
        }
        for index in range(8)
    ]
    projection_after = [
        {
            "measure": f"Tumour response rate B{index}",
            "timeFrame": "12 weeks",
            "description": "A",
            "note": "x" * 3_500,
        }
        for index in range(8)
    ]
    original_projection_identity = endpoint_alignment._projection_identity
    original_with_hash = endpoint_alignment._with_hash

    def guarded_projection_identity(payload: dict) -> dict:
        if payload.get("available") is True:
            raise AssertionError("over-cap projection identity must not be hashed")
        return original_projection_identity(payload)

    def guarded_with_hash(payload: object, field: str) -> dict:
        if (
            field == "projection_payload_sha256"
            and isinstance(payload, dict)
            and payload.get("available") is True
        ):
            raise AssertionError("over-cap projection must not be canonicalized or hashed")
        return original_with_hash(payload, field)

    monkeypatch.setattr(
        endpoint_alignment, "_projection_identity", guarded_projection_identity
    )
    monkeypatch.setattr(endpoint_alignment, "_with_hash", guarded_with_hash)

    _snapshots, _diff, projection = _projection(
        _study(outcomes=projection_before), _study(outcomes=projection_after)
    )

    assert projection["available"] is False
    assert projection["unavailable_reason"] == "projection_byte_limit_exceeded"
    assert projection["candidate_count"] == 0
    assert projection["candidates"] == []


def test_corrected_next_version_has_a_distinct_candidate_identity() -> None:
    spelling = FIXTURE["spelling_correction"]
    snapshots, first_diff, first_projection = _projection(
        _study(outcomes=[spelling["before"]]), _study(outcomes=[spelling["after"]])
    )
    corrected_study = _study(
        outcomes=[
            {
                "measure": "Tumour response rates",
                "timeFrame": "12 weeks",
                "description": "Independent central review",
            }
        ]
    )
    corrected_snapshot = _next_immutable_snapshot(snapshots[1], corrected_study)
    corrected_diff = build_history_exact_diff(
        snapshots[1], corrected_snapshot, transaction_from=corrected_snapshot["transaction_from"]
    )
    corrected_projection = build_trial_endpoint_alignment_review_projection(
        snapshots[1], corrected_snapshot, corrected_diff
    )

    assert first_projection["candidate_count"] == corrected_projection["candidate_count"] == 1
    assert first_diff["diff_id"] != corrected_diff["diff_id"]
    assert (
        first_projection["candidates"][0]["candidate_id"]
        != corrected_projection["candidates"][0]["candidate_id"]
    )
