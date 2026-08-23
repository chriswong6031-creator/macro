from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import subprocess

import pytest

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    EvidenceFoundationError,
    combined_violations,
    compute_reference_id,
    load_vocabulary,
    render_owner_pointer,
    validate_reference,
)
from scripts.worktree_sparse import missing_dirs


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "evidence_foundation"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence_foundation"
SCHEMA_PATH = CONTRACT_DIR / "reference.v1.schema.json"
VOCABULARY_PATH = CONTRACT_DIR / "vocabulary.v1.json"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return _json(SCHEMA_PATH)


@pytest.fixture(scope="module")
def vocabulary() -> dict:
    return load_vocabulary(VOCABULARY_PATH)


def _with_id(payload: dict) -> dict:
    payload["reference_id"] = compute_reference_id(payload)
    return payload


def _fixture(name: str) -> dict:
    return _json(FIXTURE_DIR / name)


def _identity_value(field: str, expected_type: str) -> str | int:
    if expected_type == "integer":
        return 1
    return {
        "nct_id": "NCT00000001",
        "filer_cik": "0000320193",
        "report_period": "2026-06-30",
        "asof": "2026-08-23",
    }.get(field, f"fixture-{field}")


def _owner_reference(name: str, owner: dict, clock_classes: list[str]) -> dict:
    identity = {
        field: _identity_value(field, owner["native_identity_types"][field])
        for field in owner["native_identity_fields"]
    }
    payload = {
        "schema": "evidence_foundation.reference.v1",
        "version": "1.0.0",
        "reference_id": "",
        "object_class": owner["object_classes"][0],
        "owner_store": name,
        "native_identity": identity,
        "native_schema": owner["native_schemas"][0],
        "native_digest": {"state": "unknown", "sha256": None},
        "coverage_class": "unknown",
        "subject": {"key_type": owner["subject_key_types"][0], "key": "fixture-subject"},
        "secondary_subjects": [],
        "clocks": [
            {
                "class": binding["class"],
                "field": field,
                "value_state": "unknown",
                "value": None,
                "grain": binding["grains"][0],
            }
            for field, binding in owner["clock_bindings"].items()
        ],
        "provenance": {
            "pointer_only": True,
            "body_embedded": False,
            "owner_reader": owner["reader"],
            "owner_reader_kind": owner["reader_kind"],
            "pointer": render_owner_pointer(owner, identity),
        },
        "relations": [],
        "missingness": {"state": "present", "reason": None, "zero_substituted": False},
        "correction": {
            "kind": "none",
            "predecessor_reference_ids": [],
            "clock_field": None,
            "chronology_state": "not_applicable",
            "append_only": True,
            "mutates_predecessor": False,
        },
        "replay": {
            "mode": "live",
            "cutoffs": {
                clock_class: {"state": "unknown", "value": None, "grain": "date"}
                for clock_class in clock_classes
            },
            "code_revision": None,
            "input_digest": None,
            "vintage_state": "owner_native",
        },
        "authority": dict(ALL_FALSE_AUTHORITY),
    }
    return _with_id(payload)


def _resolve_reader(path: str) -> object:
    parts = path.split(".")
    for split in range(len(parts), 0, -1):
        module_name = ".".join(parts[:split])
        try:
            value: object = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name and not module_name.startswith(f"{exc.name}."):
                raise
            continue
        for attribute in parts[split:]:
            value = getattr(value, attribute)
        return value
    raise AssertionError(f"reader module is not importable: {path}")


def test_contract_and_vocabulary_are_frozen_v1(schema: dict, vocabulary: dict) -> None:
    assert schema["properties"]["schema"]["const"] == "evidence_foundation.reference.v1"
    assert schema["properties"]["version"]["const"] == "1.0.0"
    assert vocabulary["schema"] == "evidence_foundation.vocabulary.v1"
    assert vocabulary["version"] == "1.0.0"
    assert len(vocabulary["owner_stores"]) == 14
    assert "earnings.company_event" not in vocabulary["owner_stores"]
    assert "txi.episode_transition" in vocabulary["owner_stores"]
    assert "ticker_store_key" not in vocabulary["subject_key_types"]
    assert "ticker_store_key" in vocabulary["excluded_identity_types"]


def test_every_owner_has_an_exact_schema_identity_clock_and_pointer_binding(
    vocabulary: dict,
) -> None:
    for name, owner in vocabulary["owner_stores"].items():
        assert set(owner["native_identity_types"]) == set(owner["native_identity_fields"]), name
        assert owner["native_schemas"] and owner["clock_bindings"], name
        assert "synapse_asof_field" in owner, name
        reference = _owner_reference(name, owner, vocabulary["clock_classes"])
        assert validate_reference(reference, vocabulary=vocabulary) == reference
        identity = reference["native_identity"]
        first_field = owner["native_identity_fields"][0]
        alternate = dict(identity)
        alternate[first_field] = (
            identity[first_field] + "-other"
            if isinstance(identity[first_field], str)
            else identity[first_field] + 1
        )
        rows = (identity, alternate)
        pointer = render_owner_pointer(owner, identity)
        assert pointer != render_owner_pointer(owner, alternate), name
        assert [row for row in rows if render_owner_pointer(owner, row) == pointer] == [identity]


def test_vocabulary_refuses_missing_schema_identity_type_clock_and_synapse_bindings(
    vocabulary: dict, tmp_path: Path
) -> None:
    cases = (
        ("native_schemas", "vocabulary_owner_native_schemas_invalid"),
        ("native_identity_types", "vocabulary_owner_identity_types_invalid"),
        ("clock_bindings", "vocabulary_owner_clocks_missing"),
        ("synapse_asof_field", "vocabulary_synapse_asof_unspecified"),
    )
    for field, code in cases:
        hostile = deepcopy(vocabulary)
        del hostile["owner_stores"]["qledger.claim"][field]
        path = tmp_path / f"missing-{field}.json"
        path.write_text(json.dumps(hostile), encoding="utf-8")
        with pytest.raises(EvidenceFoundationError, match=code):
            load_vocabulary(path)

    unbound = deepcopy(vocabulary)
    unbound["owner_stores"]["qledger.claim"]["synapse_asof_field"] = "invented_at"
    path = tmp_path / "unbound.json"
    path.write_text(json.dumps(unbound), encoding="utf-8")
    with pytest.raises(EvidenceFoundationError, match="vocabulary_synapse_asof_unbound"):
        load_vocabulary(path)


def test_every_owner_reader_symbol_is_callable_and_kind_is_honest(vocabulary: dict) -> None:
    for name, owner in vocabulary["owner_stores"].items():
        assert callable(_resolve_reader(owner["reader"])), name
        assert owner["reader_kind"] in {"direct", "collection", "parser"}, name
    assert vocabulary["owner_stores"]["fif.packet"]["reader_kind"] == "parser"
    assert vocabulary["owner_stores"]["biocatalyst.current_source_snapshot"]["reader_kind"] == "parser"


def test_owner_vocabulary_is_bound_to_current_source_contracts(vocabulary: dict) -> None:
    from engine.company_intelligence.event_workspace import WORKSPACE_KEYS, WORKSPACE_SCHEMA
    from engine.fundamental_forensics.financial_intelligence_packet import PACKET_SCHEMA
    from engine.fundamental_forensics.raw_ledger import RAW_LEDGER_SCHEMA, TemporalClocks
    from engine.government_revenue.workspace import EVENT_CONTRACT
    from engine.institutional_census.models import CATALOG_MANIFEST_SCHEMA, RAW_RECEIPT_SCHEMA
    from engine.neuralweb.market_memory_forward_store import _SCHEMA_BY_KIND
    from engine.theme_graph.store import EDGE_KEY, EVIDENCE_KEY
    from lib.dataos.registry import load_registry

    owners = vocabulary["owner_stores"]
    security = load_registry().get("reference.security_master")
    assert security is not None and security.grain == ("security_id",)
    assert owners["reference.security_master"]["native_schemas"] == [security.dataset_id]
    assert set(owners["reference.security_master"]["clock_bindings"]) <= set(security.schema)
    assert owners["theme_graph.evidence"]["native_identity_fields"] == list(EVIDENCE_KEY)
    assert owners["theme_graph.edge_belief"]["native_identity_fields"] == list(EDGE_KEY)
    assert owners["fif.raw_occurrence"]["native_schemas"] == [f"{RAW_LEDGER_SCHEMA}#RawFactOccurrence"]
    assert set(owners["fif.raw_occurrence"]["clock_bindings"]) == {
        f"clocks.{field}" for field in TemporalClocks.__dataclass_fields__
    }
    assert owners["fif.packet"]["native_schemas"] == [PACKET_SCHEMA]
    assert owners["earnings.workspace_generation"]["native_schemas"] == [WORKSPACE_SCHEMA]
    assert {"event_id", "generation_id", "generated_at", "lifecycle"} <= set(WORKSPACE_KEYS)
    assert owners["institutional_13f.raw_receipt"]["native_schemas"] == [RAW_RECEIPT_SCHEMA]
    assert owners["institutional_13f.catalog_generation"]["native_schemas"] == [CATALOG_MANIFEST_SCHEMA]
    assert owners["govrev.event.v2"]["native_schemas"] == [EVENT_CONTRACT]
    assert owners["market_memory.outcome_record"]["native_schemas"] == [_SCHEMA_BY_KIND["outcome"]]


def test_biocatalyst_current_and_history_bind_real_wire_fields(vocabulary: dict) -> None:
    current_schema = _json(ROOT / "contracts/biocatalyst/trial_source_snapshot.v1.schema.json")
    history_schema = _json(ROOT / "contracts/biocatalyst/trial_history_source_snapshot.v1.schema.json")
    current = vocabulary["owner_stores"]["biocatalyst.current_source_snapshot"]
    history = vocabulary["owner_stores"]["biocatalyst.history_source_snapshot"]
    assert current["native_identity_fields"] == ["nct_id", "source_snapshot_id"]
    assert history["native_identity_fields"] == ["nct_id", "source_version", "source_snapshot_id"]
    assert history["native_identity_types"]["source_version"] == "integer"
    assert set(current["native_identity_fields"]) <= set(current_schema["required"])
    assert set(current["clock_bindings"]) <= set(current_schema["required"])
    assert set(history["native_identity_fields"]) <= set(history_schema["required"])
    assert set(history["clock_bindings"]) <= set(history_schema["required"])


def test_txi_full_native_key_prevents_episode_aliasing(vocabulary: dict) -> None:
    from engine.transmission_chains import _ledger_key

    owner = vocabulary["owner_stores"]["txi.episode_transition"]
    row_a = {"chain": "supply", "rev": 1, "episode_id": "episode-1", "transition": "ARMED", "hop": 1, "asof": "2026-08-23"}
    row_b = {**row_a, "transition": "TRIPPED", "hop": 2}
    assert row_a["episode_id"] == row_b["episode_id"]
    assert _ledger_key(row_a) != _ledger_key(row_b)
    assert tuple(owner["native_identity_fields"]) == ("chain", "rev", "episode_id", "transition", "hop", "asof")
    assert render_owner_pointer(owner, row_a) != render_owner_pointer(owner, row_b)
    assert [row for row in (row_a, row_b) if _ledger_key(row) == _ledger_key(row_a)] == [row_a]


def test_earnings_pointer_selects_one_immutable_workspace(vocabulary: dict) -> None:
    owner = vocabulary["owner_stores"]["earnings.workspace_generation"]
    first = {"generation_id": "a" * 24, "event_id": "evt_cik0000320193_2026q3_results"}
    second = {"generation_id": "b" * 24, "event_id": first["event_id"]}
    assert render_owner_pointer(owner, first) != render_owner_pointer(owner, second)
    payload = _fixture("earnings_workspace_valid.json")
    assert payload["provenance"]["pointer"] == render_owner_pointer(owner, payload["native_identity"])


def test_fixture_manifest_is_complete_and_byte_receipted() -> None:
    manifest = _json(MANIFEST_PATH)
    assert manifest["schema"] == "evidence_foundation.fixture_manifest.v1"
    assert len(manifest["fixtures"]) == 8
    assert len({row["file"] for row in manifest["fixtures"]}) == 8
    for row in manifest["fixtures"]:
        payload = (FIXTURE_DIR / row["file"]).read_bytes()
        assert payload.endswith(b"\n")
        assert len(payload) == row["size_bytes"]
        assert sha256(payload).hexdigest() == row["sha256"]


EXPECTED_VIOLATIONS = {
    "duplicate_corroboration_hostile.json": {"relation_0_independence_not_declarative:source_independence"},
    "replay_lookahead_hostile.json": {"replay_lookahead:clocks.accepted_at", "replay_lookahead:clocks.recorded_at"},
    "authority_leak_hostile.json": {"authority_leak"},
}


def test_all_golden_fixtures_use_the_combined_fail_closed_validator(vocabulary: dict) -> None:
    for row in _json(MANIFEST_PATH)["fixtures"]:
        payload = _fixture(row["file"])
        violations = set(combined_violations(payload, vocabulary=vocabulary))
        assert payload["reference_id"] == compute_reference_id(payload), row["file"]
        if row["expected"] == "valid":
            assert validate_reference(payload, vocabulary=vocabulary) == payload
            assert not violations
        else:
            assert EXPECTED_VIOLATIONS[row["file"]] <= violations
            with pytest.raises(EvidenceFoundationError):
                validate_reference(payload, vocabulary=vocabulary)


def test_every_owner_native_schema_and_clock_is_required_exactly_once(vocabulary: dict) -> None:
    for name, owner in vocabulary["owner_stores"].items():
        valid = _owner_reference(name, owner, vocabulary["clock_classes"])
        bad_schema = deepcopy(valid)
        bad_schema["native_schema"] = "invented.schema"
        _with_id(bad_schema)
        assert "native_schema_not_owned" in combined_violations(bad_schema, vocabulary=vocabulary)
        missing_schema = deepcopy(valid)
        del missing_schema["native_schema"]
        _with_id(missing_schema)
        assert combined_violations(missing_schema, vocabulary=vocabulary)
        for field in owner["clock_bindings"]:
            missing = deepcopy(valid)
            missing["clocks"] = [clock for clock in missing["clocks"] if clock["field"] != field]
            _with_id(missing)
            assert f"clock_field_missing:{field}" in combined_violations(missing, vocabulary=vocabulary)
            duplicate = deepcopy(valid)
            duplicate["clocks"].append(deepcopy(next(clock for clock in duplicate["clocks"] if clock["field"] == field)))
            _with_id(duplicate)
            assert f"clock_field_duplicate:{field}" in combined_violations(duplicate, vocabulary=vocabulary)


def test_native_identity_types_and_pointer_are_fail_closed(vocabulary: dict) -> None:
    owner = vocabulary["owner_stores"]["txi.episode_transition"]
    valid = _owner_reference("txi.episode_transition", owner, vocabulary["clock_classes"])
    wrong_type = deepcopy(valid)
    wrong_type["native_identity"]["hop"] = "1"
    wrong_type["provenance"]["pointer"] = render_owner_pointer(owner, wrong_type["native_identity"])
    _with_id(wrong_type)
    assert "native_identity_type_mismatch:hop" in combined_violations(wrong_type, vocabulary=vocabulary)
    wrong_pointer = deepcopy(valid)
    wrong_pointer["provenance"]["pointer"] += "-alias"
    _with_id(wrong_pointer)
    assert "owner_pointer_mismatch" in combined_violations(wrong_pointer, vocabulary=vocabulary)


def test_duplicate_hostile_is_independence_only_and_not_fixed_by_disabling_effect(vocabulary: dict) -> None:
    hostile = _fixture("duplicate_corroboration_hostile.json")
    relation = hostile["relations"][0]
    assert relation["automatic_effect"] is False and relation["deterministic_key"] is None
    violations = set(combined_violations(hostile, vocabulary=vocabulary))
    assert "relation_0_independence_not_declarative:source_independence" in violations
    assert not {code for code in violations if "automatic" in code}


def _automatic_relation(reference: dict) -> dict:
    reference["relations"] = [{
        "target_reference_id": "efr_" + "1" * 64,
        "type": "exact_duplicate",
        "automatic_effect": True,
        "deterministic_key": "owner:schema/native-id",
        "independence": {
            axis: {"state": "not_assessed", "assessment": "declarative_unverified", "basis": "dedup identity does not assert independent evidence"}
            for axis in ("source_independence", "information_novelty", "mechanism_independence")
        },
    }]
    return _with_id(reference)


@pytest.mark.parametrize("key", ["", " ", "UPPER", " leading", "trailing "])
def test_deterministic_key_rejects_empty_whitespace_and_noncanonical_text(key: str, vocabulary: dict) -> None:
    valid = _owner_reference("theme_graph.evidence", vocabulary["owner_stores"]["theme_graph.evidence"], vocabulary["clock_classes"])
    hostile = _automatic_relation(valid)
    hostile["relations"][0]["deterministic_key"] = key
    _with_id(hostile)
    assert combined_violations(hostile, vocabulary=vocabulary)


def test_correction_relations_equal_predecessors_with_the_right_kind(vocabulary: dict) -> None:
    valid = _fixture("correction_append_valid.json")
    assert validate_reference(valid, vocabulary=vocabulary) == valid
    assert valid["correction"]["chronology_state"] == "owner_clock_order_not_verified"
    cases = (
        (lambda value: value["relations"].clear(), "correction_relation_missing_target"),
        (lambda value: value["relations"][0].update(target_reference_id="efr_" + "3" * 64), "correction_relation_missing_target"),
        (lambda value: value["relations"][0].update(type="corrects"), "correction_relation_wrong_kind"),
        (lambda value: value["relations"].append({**deepcopy(value["relations"][0]), "target_reference_id": "efr_" + "4" * 64}), "correction_relation_extra_target"),
    )
    for mutate, expected in cases:
        hostile = deepcopy(valid)
        mutate(hostile)
        _with_id(hostile)
        assert expected in combined_violations(hostile, vocabulary=vocabulary)
    no_chronology = deepcopy(valid)
    del no_chronology["correction"]["chronology_state"]
    _with_id(no_chronology)
    assert combined_violations(no_chronology, vocabulary=vocabulary)


def test_replay_refuses_lookahead_and_distinguishes_recomputation(vocabulary: dict) -> None:
    valid = _fixture("replay_valid.json")
    hostile = _fixture("replay_lookahead_hostile.json")
    assert validate_reference(valid, vocabulary=vocabulary) == valid
    violations = set(combined_violations(hostile, vocabulary=vocabulary))
    assert "replay_lookahead:clocks.accepted_at" in violations
    assert "replay_lookahead:clocks.recorded_at" in violations
    mislabeled = deepcopy(valid)
    mislabeled["replay"]["vintage_state"] = "current_rule_recomputation"
    _with_id(mislabeled)
    assert "recomputation_mislabeled_replay" in combined_violations(mislabeled, vocabulary=vocabulary)


@pytest.mark.parametrize("clock_class", ["world_valid", "source_published", "knowable", "observed", "system_recorded", "belief_or_build", "review_due"])
def test_every_known_replay_cutoff_is_parsed_even_when_unused(clock_class: str, vocabulary: dict) -> None:
    valid = _fixture("fif_packet_valid.json")
    valid["replay"]["cutoffs"][clock_class] = {"state": "known", "value": "2026-02-31", "grain": "date"}
    _with_id(valid)
    assert f"replay_cutoff_invalid:{clock_class}" in combined_violations(valid, vocabulary=vocabulary)


def test_same_day_date_datetime_comparisons_are_ambiguous_symmetrically(vocabulary: dict) -> None:
    datetime_clock = _fixture("replay_valid.json")
    datetime_clock["replay"]["cutoffs"]["source_published"] = {"state": "known", "value": "2026-07-30", "grain": "date"}
    _with_id(datetime_clock)
    assert "replay_grain_ambiguous:clocks.accepted_at" in combined_violations(datetime_clock, vocabulary=vocabulary)
    owner = vocabulary["owner_stores"]["theme_graph.evidence"]
    date_clock = _owner_reference("theme_graph.evidence", owner, vocabulary["clock_classes"])
    published = next(clock for clock in date_clock["clocks"] if clock["field"] == "published_at")
    published.update(value_state="known", value="2026-07-30")
    date_clock["replay"].update(mode="historical_replay", code_revision="fixture-code", input_digest="5" * 64, vintage_state="owner_native")
    date_clock["replay"]["cutoffs"]["source_published"] = {"state": "known", "value": "2026-07-30T23:59:59Z", "grain": "datetime"}
    _with_id(date_clock)
    assert "replay_grain_ambiguous:published_at" in combined_violations(date_clock, vocabulary=vocabulary)


def test_typed_missingness_and_authority_never_default_up(vocabulary: dict) -> None:
    payload = _fixture("typed_missingness_valid.json")
    assert validate_reference(payload, vocabulary=vocabulary) == payload
    assert payload["missingness"] == {"state": "absent", "reason": "unsupported", "zero_substituted": False}
    zero = deepcopy(payload)
    zero["missingness"]["zero_substituted"] = True
    _with_id(zero)
    assert "missingness_zero_substitution" in combined_violations(zero, vocabulary=vocabulary)
    leak = _fixture("authority_leak_hostile.json")
    assert "authority_leak" in combined_violations(leak, vocabulary=vocabulary)
    absent = _fixture("fif_packet_valid.json")
    del absent["authority"]
    _with_id(absent)
    assert "authority_not_materialized" in combined_violations(absent, vocabulary=vocabulary)


def test_combined_validator_rejects_embedded_owner_body(vocabulary: dict) -> None:
    payload = _fixture("fif_packet_valid.json")
    payload["body"] = {"copied_owner_truth": True}
    _with_id(payload)
    violations = combined_violations(payload, vocabulary=vocabulary)
    assert any(code.startswith("json_schema:$:additionalProperties") for code in violations)
    with pytest.raises(EvidenceFoundationError):
        validate_reference(payload, vocabulary=vocabulary)


def test_reference_id_is_deterministic_and_has_no_join_write_clock() -> None:
    payload = _fixture("fif_packet_valid.json")
    assert compute_reference_id(payload) == payload["reference_id"]
    replayed = json.loads(json.dumps(payload, sort_keys=False))
    assert compute_reference_id(replayed) == payload["reference_id"]
    assert "join_recorded_at" not in payload and "join_as_of" not in payload


def test_k1_changed_file_inventory_creates_no_physical_mesh_store() -> None:
    assert isinstance(missing_dirs(ROOT), list)  # observed, never used as absence proof
    commands = (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    changed: set[str] = set()
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        changed.update(result.stdout.splitlines())
    forbidden_prefixes = ("data/evidence_mesh/", "data/evidence_foundation/", "engine/evidence_mesh/")
    assert not [path for path in sorted(changed) if any(path.startswith(prefix) for prefix in forbidden_prefixes)]
