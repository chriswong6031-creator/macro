"""tests/test_biocatalyst_change_tape_values.py — exact Change Tape values.

The Change Tape used to serve a field-class ledger only: ``field_class``,
``op``, ``before_state``/``after_state`` in {missing, present}, source versions
and an observed clock.  A reader could not see WHAT changed and could not tell
a superseding edit from a first record without inferring it from ``op``.

These tests pin the additive v1 extension that closes that gap:

* every row carries the EXACT recorded before/after values and an RFC 6901
  source locator, taken byte-for-byte from the replay-verified version chain;
* every value is bounded, and a truncated value says so with the original byte
  length instead of being silently cut;
* an undisclosable value is an explicit marker with a reason — never an empty
  string, never a guess;
* correction lineage is DECLARED by the payload (which predecessor version the
  row supersedes), not inferred by the reader;
* a tampered chain fails closed, and a tape published before the extension
  keeps serving unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

import app.biocatalyst as biocatalyst_api
from engine.biocatalyst.change_tape import (
    ChangeTapeError,
    build_trial_change_tape_read_model,
    validate_trial_change_tape_read_model,
)
from engine.sector_intelligence import canonical_json_sha256, validate_contract


NCT_ID = "NCT01234567"
AUTHORITY = {
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
}


def _study(
    *,
    status: str = "RECRUITING",
    enrollment: int = 100,
    outcomes: list[dict] | None = None,
    locations: list[dict] | None = None,
) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": NCT_ID,
                "briefTitle": "Synthetic exact-value study",
            },
            "statusModule": {
                "overallStatus": status,
                "startDateStruct": {"date": "2025-01-01", "type": "ACTUAL"},
                "primaryCompletionDateStruct": {
                    "date": "2025-09-01",
                    "type": "ESTIMATED",
                },
                "completionDateStruct": {"date": "2025-12-01", "type": "ESTIMATED"},
            },
            "designModule": {
                "enrollmentInfo": {"count": enrollment, "type": "ESTIMATED"}
            },
            "contactsLocationsModule": {
                "locations": (
                    locations
                    if locations is not None
                    else [{"facility": "North Hospital", "city": "Boston"}]
                )
            },
            "outcomesModule": {
                "primaryOutcomes": (
                    outcomes
                    if outcomes is not None
                    else [{"measure": "Response rate", "timeFrame": "12 weeks"}]
                ),
                "secondaryOutcomes": [],
                "otherOutcomes": [],
            },
            "armsInterventionsModule": {
                "interventions": [{"name": "X-101", "type": "DRUG"}]
            },
        }
    }


def _snapshot(study: dict, *, source_version: int) -> dict:
    content_hash = canonical_json_sha256(study)
    run_ref = f"ctgov_history_run_{NCT_ID}_change_tape_value_fixture"
    seed = canonical_json_sha256(
        {
            "nct_id": NCT_ID,
            "source_version": source_version,
            "canonical_content_sha256": content_hash,
            "run_ref": run_ref,
        }
    )
    payload = {
        "contract_id": "trial_history_source_snapshot.v1",
        "schema_version": "1.0.0",
        "source_snapshot_id": f"ctgov_history_snapshot_{NCT_ID}_{seed[:24]}",
        "nct_id": NCT_ID,
        "source_id": "clinicaltrials_gov_record_history",
        "run_ref": run_ref,
        "history_index_receipt_ref": f"ctgov_history_receipt_{NCT_ID}_index",
        "history_version_receipt_ref": (
            f"ctgov_history_receipt_{NCT_ID}_version_{source_version}"
        ),
        "source_version": source_version,
        "display_version": source_version + 1,
        "source_record_ref": (
            f"src:ctgov-history:{NCT_ID}:version:{source_version}:sha256:{content_hash}"
        ),
        "source_uri": (
            f"https://clinicaltrials.gov/study/{NCT_ID}"
            f"?a={source_version + 1}&tab=history"
        ),
        "source_submitted_at": f"2025-0{source_version + 1}-01",
        "source_last_update_submit_qc_at": f"2025-0{source_version + 1}-02",
        "canonical_study": deepcopy(study),
        "canonical_content_sha256": content_hash,
        "retrieved_at": f"2026-08-0{source_version + 2}T00:00:02Z",
        "source_fact": True,
        "current_only": False,
        "coverage_class": "record_history_complete",
        "authority": deepcopy(AUTHORITY),
        "transaction_from": f"2026-08-0{source_version + 2}T00:00:04Z",
        "transaction_to": None,
        "hash_scope": "canonical_payload_excluding_snapshot_payload_sha256",
    }
    payload["snapshot_payload_sha256"] = canonical_json_sha256(payload)
    validate_contract(payload)
    return payload


def _tape(*studies: dict) -> dict:
    snapshots = tuple(
        _snapshot(study, source_version=index) for index, study in enumerate(studies)
    )
    return build_trial_change_tape_read_model(
        nct_id=NCT_ID,
        history_model={"available": True},
        history_snapshots=snapshots,
        history_carried_forward=False,
        prospective_model=None,
    )


def _rows_by_pointer(tape: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in tape["history"]["rows"]:
        grouped.setdefault(row["exact_values"]["source_pointer"], []).append(row)
    return grouped


def _reseal(tape: dict) -> dict:
    tape["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in tape.items() if key != "model_payload_sha256"}
    )
    return tape


def test_change_tape_discloses_exact_values_and_source_locator_from_the_chain() -> None:
    """Values are the recorded canonical JSON bytes, never a normalized copy."""

    # Deliberately awkward source text: mixed case, inner whitespace, a unicode
    # dash and a trailing space.  A normalizing implementation would "clean"
    # any of these and stop being an exact quotation of the record.
    exact_measure = "Overall  Response Rate — RECIST v1.1 "
    tape = _tape(
        _study(),
        _study(
            status="ACTIVE_NOT_RECRUITING",
            enrollment=144,
            outcomes=[{"measure": exact_measure, "timeFrame": "12 weeks"}],
        ),
    )
    validate_trial_change_tape_read_model(tape, nct_id=NCT_ID)

    assert tape["value_disclosure"] == {
        "state": "exact_values_present",
        "encoding": "canonical_json_utf8",
        "locator_grammar": "rfc6901_json_pointer_into_source_record",
        "max_value_bytes": 4096,
        "max_tape_value_bytes": 262144,
        "truncation_behavior": "declared_prefix_with_original_byte_length",
        "unavailable_behavior": "explicit_row_marker_never_empty_and_never_guessed",
        "correction_assessed": False,
    }

    grouped = _rows_by_pointer(tape)
    status_row = grouped["/protocolSection/statusModule/overallStatus"][0]
    assert status_row["op"] == "replace"
    assert status_row["exact_values"]["before"]["value_json"] == '"RECRUITING"'
    assert (
        status_row["exact_values"]["after"]["value_json"]
        == '"ACTIVE_NOT_RECRUITING"'
    )
    assert status_row["exact_values"]["before"]["value_truncated"] is False
    assert status_row["exact_values"]["before"]["value_byte_length"] == len(
        '"RECRUITING"'.encode("utf-8")
    )

    enrollment_row = grouped[
        "/protocolSection/designModule/enrollmentInfo/count"
    ][0]
    assert enrollment_row["exact_values"]["before"]["value_json"] == "100"
    assert enrollment_row["exact_values"]["after"]["value_json"] == "144"

    outcome_row = grouped["/protocolSection/outcomesModule/primaryOutcomes"][0]
    after_value = json.loads(outcome_row["exact_values"]["after"]["value_json"])
    assert after_value == [{"measure": exact_measure, "timeFrame": "12 weeks"}]
    # Byte-exact, not merely equal after re-parsing: the disclosed text keeps
    # the trailing space and the em dash exactly as the registry recorded them.
    assert exact_measure in outcome_row["exact_values"]["after"]["value_json"]
    assert "—" in outcome_row["exact_values"]["after"]["value_json"]

    # A locator, not a private store path: it resolves inside the source record.
    for row in tape["history"]["rows"]:
        pointer = row["exact_values"]["source_pointer"]
        assert pointer.startswith("/protocolSection/")
        assert "source_json_path" not in row
        assert not any(
            fragment in key
            for key in row
            for fragment in ("hash", "receipt", "snapshot", "raw")
        )


def test_change_tape_states_add_and_remove_values_without_empty_string_guesses() -> None:
    """A missing side is an explicit marker, never an empty or invented value."""

    added = _tape(
        _study(locations=[]),
        _study(locations=[{"facility": "North Hospital", "city": "Boston"}]),
    )
    grouped = _rows_by_pointer(added)
    row = grouped["/protocolSection/contactsLocationsModule/locations"][0]
    assert row["op"] == "replace"
    assert row["exact_values"]["before"]["value_json"] == "[]"

    removed = _tape(
        _study(
            outcomes=[
                {"measure": "Response rate", "timeFrame": "12 weeks"},
            ]
        ),
        _study(outcomes=[]),
    )
    outcome_row = _rows_by_pointer(removed)[
        "/protocolSection/outcomesModule/primaryOutcomes"
    ][0]
    assert outcome_row["exact_values"]["after"]["value_json"] == "[]"
    assert outcome_row["exact_values"]["after"]["state"] == "present"

    # A structurally missing side (a key that only exists on one side) is the
    # "missing" marker with no value at all — not "" and not null-as-a-value.
    before_study = _study()
    after_study = _study()
    after_study["protocolSection"]["statusModule"]["startDateStruct"][
        "extraLabel"
    ] = "phase-3 start window"
    tape = _tape(before_study, after_study)
    added_row = _rows_by_pointer(tape)[
        "/protocolSection/statusModule/startDateStruct/extraLabel"
    ][0]
    assert added_row["op"] == "add"
    assert added_row["exact_values"]["before"] == {
        "state": "missing",
        "value_json": None,
        "value_byte_length": 0,
        "value_truncated": False,
        "unavailable_reason": None,
    }
    assert (
        added_row["exact_values"]["after"]["value_json"] == '"phase-3 start window"'
    )
    assert added_row["correction_lineage"]["relation"] == "no_prior_recorded_value"
    assert added_row["correction_lineage"]["predecessor_basis"] == "none"


def test_change_tape_truncates_hostile_free_text_and_declares_the_original_length() -> None:
    """A long value is a DECLARED prefix plus its true byte length, not a cut."""

    hostile = "é" * 6_000  # 12,000 UTF-8 bytes of free text.
    tape = _tape(
        _study(),
        _study(outcomes=[{"measure": hostile, "timeFrame": "12 weeks"}]),
    )
    validate_trial_change_tape_read_model(tape, nct_id=NCT_ID)
    row = _rows_by_pointer(tape)["/protocolSection/outcomesModule/primaryOutcomes"][0]
    disclosed = row["exact_values"]["after"]

    assert disclosed["state"] == "present"
    assert disclosed["value_truncated"] is True
    assert disclosed["value_byte_length"] > 12_000
    assert len(disclosed["value_json"].encode("utf-8")) <= 4_096
    # The prefix is a real prefix of the exact recorded canonical JSON, so it
    # can be checked against the source rather than merely believed.
    full = json.dumps(
        [{"measure": hostile, "timeFrame": "12 weeks"}],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert full.startswith(disclosed["value_json"])
    assert disclosed["value_byte_length"] == len(full.encode("utf-8"))
    # Bounded payload: one hostile field cannot blow the artifact budget.
    assert len(json.dumps(tape).encode("utf-8")) < 262_144


def test_change_tape_value_budget_is_exhausted_explicitly_never_silently() -> None:
    """Past the tape budget a value is unavailable WITH a reason, not empty."""

    # Forty replaced enrollment sub-fields, each side over the per-value cap:
    # 40 rows x 2 sides x 4,096 charged bytes is well past the tape budget.
    before_study = _study()
    after_study = _study()
    for index in range(40):
        before_study["protocolSection"]["designModule"]["enrollmentInfo"][
            f"note{index:02d}"
        ] = f"before-{'z' * 5_000}"
        after_study["protocolSection"]["designModule"]["enrollmentInfo"][
            f"note{index:02d}"
        ] = f"after-{'z' * 5_000}"
    tape = _tape(before_study, after_study)
    validate_trial_change_tape_read_model(tape, nct_id=NCT_ID)

    entries = [
        entry
        for row in tape["history"]["rows"]
        for entry in (row["exact_values"]["before"], row["exact_values"]["after"])
    ]
    exhausted = [
        entry for entry in entries if entry["state"] == "unavailable"
    ]
    assert exhausted, "the fixture must actually exhaust the tape value budget"
    assert all(
        entry["unavailable_reason"] == "tape_value_budget_exhausted"
        and entry["value_json"] is None
        and entry["value_truncated"] is False
        for entry in exhausted
    )
    # Every row still ships its field class, and no row silently drops to "".
    assert all(entry["value_json"] != "" for entry in entries)
    charged = sum(
        len(entry["value_json"].encode("utf-8"))
        for entry in entries
        if entry["state"] == "present"
    )
    assert charged <= 262_144


def test_change_tape_declares_correction_lineage_instead_of_leaving_it_inferred() -> None:
    """The predecessor version is stated, so no reader infers it from ``op``."""

    tape = _tape(
        _study(status="NOT_YET_RECRUITING"),
        _study(status="RECRUITING"),
        _study(status="ACTIVE_NOT_RECRUITING"),
    )
    validate_trial_change_tape_read_model(tape, nct_id=NCT_ID)
    status_rows = _rows_by_pointer(tape)[
        "/protocolSection/statusModule/overallStatus"
    ]
    assert len(status_rows) == 2

    first, second = status_rows
    assert first["source_versions"] == {"before": 1, "after": 2}
    assert first["correction_lineage"] == {
        "relation": "supersedes_prior_recorded_value",
        "predecessor_basis": "before_version_record",
        "predecessor_source_version": 1,
        "predecessor_exact_operation_index": None,
        "correction_assessed": False,
    }
    # The second edit at the same locator names the row it supersedes exactly:
    # version 2 at that operation index, not "probably the previous pair".
    assert second["source_versions"] == {"before": 2, "after": 3}
    assert second["correction_lineage"] == {
        "relation": "supersedes_prior_recorded_value",
        "predecessor_basis": "prior_tape_row",
        "predecessor_source_version": 2,
        "predecessor_exact_operation_index": first["exact_operation_index"],
        "correction_assessed": False,
    }
    # Lineage never becomes an assessment of correction.
    assert tape["correction_assessed"] is False
    assert all(
        row["correction_assessed"] is False
        and row["correction_lineage"]["correction_assessed"] is False
        for row in tape["history"]["rows"]
    )


def test_change_tape_fails_closed_when_the_recorded_chain_is_tampered() -> None:
    """Values are only reproducible from the verified chain, never salvaged."""

    honest = _tape(_study(), _study(status="COMPLETED"))
    assert honest["history"]["available"] is True

    tampered_study = _study(status="COMPLETED")
    tampered_study["protocolSection"]["statusModule"]["overallStatus"] = "WITHDRAWN"
    forged_after = _snapshot(_study(status="COMPLETED"), source_version=1)
    forged_after["canonical_study"]["protocolSection"]["statusModule"][
        "overallStatus"
    ] = "WITHDRAWN"

    tape = build_trial_change_tape_read_model(
        nct_id=NCT_ID,
        history_model={"available": True},
        history_snapshots=(_snapshot(_study(), source_version=0), forged_after),
        history_carried_forward=False,
        prospective_model=None,
    )
    assert tape["history"]["available"] is False
    assert tape["history"]["unavailable_reason"] == (
        "retrospective_evidence_replay_failed"
    )
    assert tape["history"]["rows"] == []
    assert tape["value_disclosure"]["state"] == "exact_values_absent"


def test_change_tape_validator_rejects_forged_values_and_forged_lineage() -> None:
    """A published tape cannot be edited into a nicer story after the fact."""

    tape = _tape(
        _study(status="NOT_YET_RECRUITING"),
        _study(status="RECRUITING"),
        _study(status="ACTIVE_NOT_RECRUITING"),
    )

    # Substituting a value is caught by the tape's own payload hash: the
    # public model carries no private evidence, so integrity is the seal.
    forged = deepcopy(tape)
    _rows_by_pointer(forged)["/protocolSection/statusModule/overallStatus"][0][
        "exact_values"
    ]["after"]["value_json"] = '"TERMINATED!"'
    with pytest.raises(ChangeTapeError, match="hash_mismatch"):
        validate_trial_change_tape_read_model(forged, nct_id=NCT_ID)

    # Resealing does not help: the declared byte length must still describe the
    # disclosed text, so a re-sealed substitution has to lie about itself.
    with pytest.raises(ChangeTapeError, match="value_bytes_invalid"):
        validate_trial_change_tape_read_model(_reseal(forged), nct_id=NCT_ID)

    forged = deepcopy(tape)
    _rows_by_pointer(forged)["/protocolSection/statusModule/overallStatus"][0][
        "exact_values"
    ]["after"]["value_json"] = ""
    # An empty string is never a value here: the contract refuses it outright,
    # so "we could not read it" can never be dressed up as "it became blank".
    with pytest.raises(ChangeTapeError, match="contract_invalid"):
        validate_trial_change_tape_read_model(_reseal(forged), nct_id=NCT_ID)

    forged = deepcopy(tape)
    _rows_by_pointer(forged)["/protocolSection/statusModule/overallStatus"][1][
        "correction_lineage"
    ]["predecessor_source_version"] = 1
    with pytest.raises(ChangeTapeError, match="lineage_invalid"):
        validate_trial_change_tape_read_model(_reseal(forged), nct_id=NCT_ID)

    forged = deepcopy(tape)
    forged["history"]["rows"][0].pop("exact_values")
    forged["history"]["rows"][0].pop("correction_lineage")
    with pytest.raises(ChangeTapeError, match="disclosure_mixed"):
        validate_trial_change_tape_read_model(_reseal(forged), nct_id=NCT_ID)

    forged = deepcopy(tape)
    forged.pop("value_disclosure")
    with pytest.raises(ChangeTapeError, match="value_disclosure_undeclared"):
        validate_trial_change_tape_read_model(_reseal(forged), nct_id=NCT_ID)

    forged = deepcopy(tape)
    forged["value_disclosure"]["state"] = "exact_values_absent"
    with pytest.raises(ChangeTapeError, match="value_disclosure_invalid"):
        validate_trial_change_tape_read_model(_reseal(forged), nct_id=NCT_ID)


def test_change_tape_extension_is_optional_so_prior_artifacts_stay_valid() -> None:
    """A tape published before this extension keeps validating and carrying."""

    legacy = _tape(_study(), _study(status="COMPLETED"))
    for row in legacy["history"]["rows"]:
        row.pop("exact_values")
        row.pop("correction_lineage")
    legacy.pop("value_disclosure")
    _reseal(legacy)

    validate_trial_change_tape_read_model(legacy, nct_id=NCT_ID)

    # Carry-forward copies that older lane byte-for-byte; the rebuilt envelope
    # must then declare the absence rather than claim values it does not have.
    carried = build_trial_change_tape_read_model(
        nct_id=NCT_ID,
        history_model={"available": True},
        history_snapshots=(),
        history_carried_forward=True,
        carried_history_lane=legacy["history"],
        prospective_model=None,
    )
    assert carried["history"] == legacy["history"]
    assert carried["value_disclosure"]["state"] == "exact_values_absent"
    validate_trial_change_tape_read_model(carried, nct_id=NCT_ID)


def test_change_tape_api_serves_exact_values_and_revalidates_them_at_request_time() -> None:
    """The serving process re-proves the disclosure contract on every read."""

    tape = _tape(
        _study(status="NOT_YET_RECRUITING"),
        _study(status="RECRUITING"),
        _study(status="ACTIVE_NOT_RECRUITING"),
    )
    state, reason, rows = biocatalyst_api._change_tape_model_rows(tape, nct_id=NCT_ID)
    assert (state, reason) == ("available", None)
    status_rows = [
        row
        for row in rows
        if row["exact_values"]["source_pointer"]
        == "/protocolSection/statusModule/overallStatus"
    ]
    assert len(status_rows) == 2
    assert status_rows[0]["exact_values"]["before"]["value_json"] == (
        '"NOT_YET_RECRUITING"'
    )
    assert status_rows[1]["exact_values"]["after"]["value_json"] == (
        '"ACTIVE_NOT_RECRUITING"'
    )
    assert status_rows[1]["correction_lineage"]["predecessor_basis"] == (
        "prior_tape_row"
    )
    assert all(row["correction_assessed"] is False for row in rows)

    # A tape whose truncation flag lies about the value it carries is refused
    # by the API even though the artifact validated at publication time.
    forged = deepcopy(tape)
    forged["history"]["rows"][0]["exact_values"]["after"]["value_truncated"] = True
    with pytest.raises(Exception):
        biocatalyst_api._change_tape_model_rows(forged, nct_id=NCT_ID)

    # So is a tape that carries values without declaring them.
    forged = deepcopy(tape)
    forged.pop("value_disclosure")
    with pytest.raises(Exception):
        biocatalyst_api._change_tape_model_rows(forged, nct_id=NCT_ID)

    # So is forged lineage.
    forged = deepcopy(tape)
    forged["history"]["rows"][-1]["correction_lineage"]["predecessor_basis"] = "none"
    with pytest.raises(Exception):
        biocatalyst_api._change_tape_model_rows(forged, nct_id=NCT_ID)


def test_change_tape_api_still_serves_a_pre_extension_tape_unchanged() -> None:
    """Old readers and old artifacts keep working: the extension is additive."""

    legacy = _tape(_study(), _study(status="COMPLETED"))
    for row in legacy["history"]["rows"]:
        row.pop("exact_values")
        row.pop("correction_lineage")
    legacy.pop("value_disclosure")
    _reseal(legacy)

    state, reason, rows = biocatalyst_api._change_tape_model_rows(
        legacy, nct_id=NCT_ID
    )
    assert (state, reason) == ("available", None)
    assert rows
    assert all("exact_values" not in row for row in rows)
    assert all("correction_lineage" not in row for row in rows)
