"""Rail gates for the exact IDV child bridge into prime-award dossiers.

One test per Wave 10 acceptance gate, plus the three published bridge states and
the honest-zero requirement.  Every gate is written so that removing the
protection it names makes the test fail.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from engine.government_revenue.dossiers import DOSSIER_CONTRACT
from engine.government_revenue.idv_dossiers import (
    AUTHORITY as IDV_AUTHORITY,
    IDV_DOSSIER_CONTRACT,
    build_idv_dossier_payload,
)
from engine.government_revenue.idv_bridge import (
    ABSTAINING_OMISSION_CODES,
    AUTHORITY,
    BRIDGE_STATES,
    IDV_BRIDGE_CONTRACT,
    _bridge_key,
    award_bridge_view,
    build_idv_bridge_payload,
    idv_bridge_content_id,
    is_valid_idv_bridge_payload,
    source_native_parent_idv_id,
)
from tests.test_government_revenue_idv_dossiers import CHILD, GRANDCHILD, PARENT, _write_bundle


CONTRACT_PATH = (
    Path(__file__).parents[1] / "contracts" / "government_revenue" / "government_idv_bridge.v1.schema.json"
)
CHILD_AWARD_KEY = "generated:" + CHILD
#: A task order whose own composite identity names PARENT as its parent award.
TUPLE_CHILD = "CONT_AWD_TUPLEORDER_1010_PARENT_1010"


def _prime_payload(*generated_ids: str, as_of: str = "2026-08-02") -> dict[str, Any]:
    return {
        "contract": DOSSIER_CONTRACT,
        "content_id": "grd1-" + "0" * 24,
        "as_of": as_of,
        "awards": [
            {
                "award_key": "generated:" + generated_id,
                "identity": {"generated_award_id": generated_id, "kind": "generated_award_id"},
                "recipient": {"name": "A PUBLIC COMPANY", "uei": "EZZLZJRCKRC3"},
            }
            for generated_id in generated_ids
        ],
    }


def _forge(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy for tampering, ready for :func:`_reseal`."""
    return json.loads(json.dumps(payload))


def _reseal(payload: dict[str, Any]) -> dict[str, Any]:
    """Make a forgery internally self-consistent before validating it.

    Without this, every tampered payload is caught by the derived ``bridge_key``
    and ``content_id`` alone, so the semantic rule under test never runs and the
    assertion passes for the wrong reason.
    """
    for row in payload["bridges"]:
        identity = row["identity"]
        row["bridge_key"] = _bridge_key(
            row["state"],
            identity["idv_generated_award_id"],
            identity["bridged_generated_award_id"] or identity["idv_generated_award_id"],
            row["award_key"],
            row["evidence"]["basis"],
        )
    grouped: dict[str, list[str]] = {}
    states: dict[str, set[str]] = {}
    for row in payload["bridges"]:
        # Mirror the builder exactly: vehicle-scoped readings never enter an
        # award envelope.  A looser mirror here would let the envelope check
        # catch forgeries that the state rules are supposed to catch.
        if row["award_key"] is None or row["state"] == "count_only":
            continue
        grouped.setdefault(row["award_key"], []).append(row["bridge_key"])
        states.setdefault(row["award_key"], set()).add(row["state"])
    payload["awards"] = [
        {
            "award_key": award_key,
            "bridge_keys": sorted(grouped[award_key]),
            "bridge_count": len(grouped[award_key]),
            "states": sorted(states[award_key]),
        }
        for award_key in sorted(grouped)
    ]
    payload["counts"]["bridged_award_count"] = len(payload["awards"])
    payload["content_id"] = idv_bridge_content_id(payload)
    return payload


def _bridge(tmp_path: Path, *generated_ids: str, **kwargs: Any) -> dict[str, Any]:
    idv = build_idv_dossier_payload(
        tmp_path,
        prime_award_key_by_generated_id={
            generated_id: "generated:" + generated_id
            for generated_id in generated_ids
            if generated_id.startswith("CONT_AWD_")
        },
        as_of="2026-08-02",
    )
    return build_idv_bridge_payload(
        idv_payload=idv,
        prime_payload=_prime_payload(*generated_ids),
        as_of="2026-08-02",
        **kwargs,
    )


def test_source_native_parent_tuple_is_exact_or_absent() -> None:
    """Only USAspending's own canonical composite identity yields a parent."""
    assert source_native_parent_idv_id(TUPLE_CHILD) == PARENT
    assert source_native_parent_idv_id("CONT_AWD_NNK15MA50T_8000_NNK14MA75C_8000") == (
        "CONT_IDV_NNK14MA75C_8000"
    )
    # The publisher's explicit no-parent sentinel is never turned into a vehicle.
    assert source_native_parent_idv_id("CONT_AWD_1305M222PNMAN0035_1330_-NONE-_-NONE-") is None
    # A non-canonical component count is abstained on, never split heuristically.
    # ``CHILD`` is exactly this case: its PIID itself carries an underscore.
    assert CHILD.count("_") == 6
    assert source_native_parent_idv_id(CHILD) is None
    assert source_native_parent_idv_id("CONT_AWD_ORDER_1010") is None
    assert source_native_parent_idv_id("CONT_IDV_PARENT_1010") is None
    assert source_native_parent_idv_id(None) is None


def test_task_order_state_bridges_an_enumerated_child_with_its_receipt(tmp_path: Path) -> None:
    _write_bundle(tmp_path)

    payload = _bridge(tmp_path, CHILD)

    assert payload["status"] == "observed"
    assert payload["counts"]["task_order"] == 1
    assert payload["counts"]["bridged"] == 1
    assert payload["counts"]["vehicle_membership"] == 0
    row = next(row for row in payload["bridges"] if row["state"] == "task_order")
    assert row["award_key"] == CHILD_AWARD_KEY
    assert row["identity"]["idv_generated_award_id"] == PARENT
    assert row["identity"]["bridged_generated_award_id"] == CHILD
    assert row["identity"]["relationship_depth"] == "direct_child"
    assert row["evidence"]["basis"] == "enumerated_child_award"
    assert row["evidence"]["relationship_key"].startswith("idvrel:")
    assert row["evidence"]["receipt_id"].startswith("usaspending-idv:")
    assert len(row["evidence"]["response_sha256"]) == 64
    assert payload["awards"] == [
        {
            "award_key": CHILD_AWARD_KEY,
            "bridge_keys": [row["bridge_key"]],
            "bridge_count": 1,
            "states": ["task_order"],
        }
    ]
    assert is_valid_idv_bridge_payload(payload)


def test_vehicle_membership_requires_the_award_record_to_be_the_vehicle(tmp_path: Path) -> None:
    """A seat is published only with source proof, per the handoff prohibition."""
    _write_bundle(tmp_path)

    seated = _bridge(tmp_path, PARENT)

    row = next(row for row in seated["bridges"] if row["state"] == "vehicle_membership")
    assert seated["counts"]["vehicle_membership"] == 1
    assert row["award_key"] == "generated:" + PARENT
    assert row["identity"]["bridged_generated_award_id"] == PARENT
    assert row["evidence"]["basis"] == "prime_award_record_is_the_vehicle"
    assert "own generated award ID" in row["evidence"]["source_proof"]

    # A recipient that merely holds a task order is NOT given a vehicle seat.
    ordered = _bridge(tmp_path, CHILD)
    assert ordered["counts"]["vehicle_membership"] == 0
    assert [row["state"] for row in ordered["bridges"]] == ["task_order"]
    assert any("never called a vehicle seat without source proof" in line for line in ordered["limitations"])


def test_count_only_state_names_no_child_and_claims_no_membership(tmp_path: Path) -> None:
    _write_bundle(tmp_path, high_count_only=True)

    payload = _bridge(tmp_path, CHILD)

    assert payload["counts"] == {
        "count_only": 1,
        "task_order": 0,
        "vehicle_membership": 0,
        "bridged": 0,
        "bridged_award_count": 0,
        # Nothing was enumerated and CHILD's identity is not decomposable, so the
        # one candidate award is abstained on rather than attached to the count.
        "abstained": 1,
    }
    assert [item["code"] for item in payload["omissions"]] == ["prime_award_identity_not_decomposable"]
    row = next(row for row in payload["bridges"] if row["state"] == "count_only")
    assert row["award_key"] is None
    assert row["identity"]["bridged_generated_award_id"] is None
    assert row["evidence"]["basis"] == "verified_child_count_without_enumeration"
    assert row["evidence"]["parent_count_verified"] is True
    assert row["evidence"]["parent_source_exhausted"] is False
    assert row["evidence"]["parent_reported_child_count"] == 501
    assert payload["awards"] == []
    assert "will not list" in payload["disclosure"]
    assert is_valid_idv_bridge_payload(payload)


def test_count_only_parent_admits_a_source_native_tuple_task_order(tmp_path: Path) -> None:
    """An unenumerable vehicle still bridges an award whose own ID names it."""
    _write_bundle(tmp_path, high_count_only=True)

    payload = _bridge(tmp_path, TUPLE_CHILD)

    order = next(row for row in payload["bridges"] if row["state"] == "task_order")
    assert order["award_key"] == "generated:" + TUPLE_CHILD
    assert order["identity"]["idv_generated_award_id"] == PARENT
    assert order["evidence"]["basis"] == "source_native_parent_tuple"
    assert order["evidence"]["relationship_key"] is None
    assert order["evidence"]["parent_collection_state"] == "high_count_count_only"
    assert {row["state"] for row in payload["bridges"]} == {"count_only", "task_order"}
    assert is_valid_idv_bridge_payload(payload)


def test_exhausted_enumeration_refuses_a_tuple_link_and_reports_the_disagreement(tmp_path: Path) -> None:
    """A complete child list that omits the award blocks the weaker basis."""
    _write_bundle(tmp_path)

    payload = _bridge(tmp_path, TUPLE_CHILD)

    assert payload["counts"]["bridged"] == 0
    assert payload["bridges"] == []
    omission = next(
        item for item in payload["omissions"] if item["code"] == "exhausted_enumeration_omits_named_child"
    )
    assert omission["count"] == 1
    assert "refused the link" in omission["reason"]
    assert is_valid_idv_bridge_payload(payload)


# --- Wave 10 rail acceptance gates ------------------------------------------


def test_gate_source_native_identity_and_immutable_receipts(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    payload = _bridge(tmp_path, CHILD, PARENT)

    assert payload["contract"] == IDV_BRIDGE_CONTRACT
    assert idv_bridge_content_id(payload) == payload["content_id"]
    assert payload["source_bindings"]["idv_content_id"].startswith("griv1-")
    assert payload["source_bindings"]["idv_selection_manifest_id"].startswith("idvsel1-")
    for row in payload["bridges"]:
        assert row["identity"]["idv_generated_award_id"].startswith("CONT_IDV_")
        assert row["evidence"]["parent_count_verified"] is True
        if row["evidence"]["basis"] == "enumerated_child_award":
            assert row["evidence"]["receipt_id"] and row["evidence"]["response_sha256"]

    # The identity is content-addressed: any published field change re-keys it,
    # and the assembly clock is deliberately excluded from that identity.
    mutated = json.loads(json.dumps(payload))
    mutated["counts"]["task_order"] += 1
    assert idv_bridge_content_id(mutated) != payload["content_id"]
    restamped = json.loads(json.dumps(payload))
    restamped["generated_at"] = "2030-01-01T00:00:00+00:00"
    assert idv_bridge_content_id(restamped) == payload["content_id"]


def test_gate_explicit_collection_universe_and_omission_states(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    # GRANDCHILD is enumerated by the source but absent from this award cut;
    # the outside award names a vehicle this collection never selected.
    outside = "CONT_AWD_OTHERORDER_2020_OTHERPARENT_2020"
    standalone = "CONT_AWD_SOLO_2020_-NONE-_-NONE-"
    payload = _bridge(tmp_path, CHILD, outside, standalone)

    universe = payload["collection_universe"]
    assert universe["status"] == "verified"
    assert universe["selected_parent_count"] == len(universe["selected_parent_ids"]) == 1
    assert universe["enumerated_child_count"] == 2
    assert universe["prime_award_count"] == 3
    assert universe["prime_awards_naming_a_parent_vehicle"] == 1  # outside
    assert universe["prime_awards_asserting_no_parent_vehicle"] == 1  # standalone

    codes = {item["code"]: item["count"] for item in payload["omissions"]}
    assert codes["enumerated_child_outside_prime_dossier"] == 1  # GRANDCHILD
    assert codes["prime_parent_tuple_outside_collection_universe"] == 1  # outside
    assert codes["prime_award_asserts_no_parent_vehicle"] == 1  # standalone
    # CHILD is bridged by the source's own enumeration, so its non-canonical
    # identity is never counted as an abstention.
    assert "prime_award_identity_not_decomposable" not in codes
    assert payload["counts"]["abstained"] == sum(
        count for code, count in codes.items() if code in ABSTAINING_OMISSION_CODES
    )
    # A source-asserted absence of a parent is a negative fact, not an abstention.
    assert "prime_award_asserts_no_parent_vehicle" not in ABSTAINING_OMISSION_CODES
    assert is_valid_idv_bridge_payload(payload)


def test_gate_source_effective_observed_and_known_at_stay_separate(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    payload = _bridge(tmp_path, CHILD)

    assert set(payload["clocks"]) == {"source_effective_at", "source_observed_at", "observed_at", "known_at"}
    row = next(row for row in payload["bridges"] if row["state"] == "task_order")
    assert set(row["clocks"]) == {
        "source_effective_date",
        "source_observed_at",
        "observed_at",
        "known_at",
        "first_seen_at",
    }
    # The government fact's own date is a date, not the evidence clock.
    assert row["clocks"]["source_effective_date"] == "2026-01-15"
    assert row["clocks"]["source_observed_at"] == "2026-08-02T00:00:00+00:00"
    assert row["clocks"]["known_at"] == "2026-08-02T00:00:00+00:00"
    assert row["clocks"]["source_effective_date"] != row["clocks"]["known_at"]
    assert payload["clocks"]["source_effective_at"] == "2026-01-15"
    assert payload["clocks"]["known_at"] == "2026-08-02T00:00:00+00:00"
    # A vehicle-scoped reading carries no child action date and never borrows one.
    seat = next(row for row in _bridge(tmp_path, PARENT)["bridges"])
    assert seat["clocks"]["source_effective_date"] is None
    assert seat["clocks"]["first_seen_at"] is None
    assert seat["clocks"]["known_at"] == "2026-08-02T00:00:00+00:00"


def test_gate_first_baseline_cannot_synthesize_history(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    first = _bridge(tmp_path, CHILD)

    assert first["baseline"] == {
        "status": "first_baseline",
        "history_synthesized": False,
        "prior_content_id": None,
        "prior_known_at": None,
        "reason": (
            "This is the first bridge reading. No earlier bridge history is asserted or back-filled: the "
            "counts describe this one generation only."
        ),
    }
    assert first["last_good"]["status"] == "none"

    second = _bridge(tmp_path, CHILD, previous=first)
    assert second["baseline"]["status"] == "continuing"
    assert second["baseline"]["prior_content_id"] == first["content_id"]
    assert second["baseline"]["history_synthesized"] is False

    # A payload that claims back-filled history fails public validation.
    forged = json.loads(json.dumps(first))
    forged["baseline"]["history_synthesized"] = True
    forged["content_id"] = idv_bridge_content_id(forged)
    assert not is_valid_idv_bridge_payload(forged)

    # So does a first baseline that names a predecessor it never observed.
    mislabelled = json.loads(json.dumps(first))
    mislabelled["baseline"]["prior_content_id"] = second["content_id"]
    mislabelled["content_id"] = idv_bridge_content_id(mislabelled)
    assert not is_valid_idv_bridge_payload(mislabelled)


def test_gate_no_semantic_similarity_or_name_join(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    # Same recipient name and a near-identical PIID under a different generated
    # identity: an exact-identity bridge must refuse it.
    near_miss = "CONT_AWD_CHILD_A_1010_PARENT_1011"
    payload = _bridge(tmp_path, near_miss)

    assert payload["join_policy"]["semantic_similarity_join"] is False
    assert payload["join_policy"]["name_join"] is False
    assert payload["join_policy"]["piid_only_join"] is False
    assert payload["counts"]["bridged"] == 0
    assert payload["bridges"] == []
    rendered = json.dumps(payload)
    assert "A PUBLIC COMPANY" not in rendered
    assert "THE BOEING COMPANY" not in rendered

    # A name-shaped bridge entry cannot smuggle a link in either.
    named = build_idv_dossier_payload(
        tmp_path,
        prime_award_key_by_generated_id={CHILD: "generated:recipient-name-match"},
        as_of="2026-08-02",
    )
    by_name = build_idv_bridge_payload(
        idv_payload=named,
        prime_payload=_prime_payload("CONT_AWD_UNRELATED_3030_-NONE-_-NONE-"),
        as_of="2026-08-02",
    )
    assert by_name["counts"]["bridged"] == 0


def test_gate_source_failure_cannot_erase_last_good_evidence(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    observed = _bridge(tmp_path, CHILD)
    assert observed["counts"]["bridged"] == 1

    # An uninitialized source bundle is an explicit no-reading generation.
    empty = build_idv_dossier_payload(tmp_path / "fresh", as_of="2026-08-02")
    degraded = build_idv_bridge_payload(
        idv_payload=empty,
        prime_payload=_prime_payload(CHILD),
        as_of="2026-08-02",
        previous=observed,
    )

    assert degraded["status"] == "unavailable"
    assert degraded["bridges"] == []
    assert all(count == 0 for count in degraded["counts"].values())
    assert degraded["last_good"] == {
        "status": "retained",
        "content_id": observed["content_id"],
        "known_at": observed["clocks"]["known_at"],
        "counts": observed["counts"],
        "reason": "The last complete bridge reading is kept so a source failure cannot erase it.",
    }
    assert "not an observation of zero" in degraded["disclosure"]
    assert is_valid_idv_bridge_payload(degraded)

    # A second consecutive failure forwards the same last-good, never its zeros.
    still_down = build_idv_bridge_payload(
        idv_payload=empty,
        prime_payload=_prime_payload(CHILD),
        as_of="2026-08-02",
        previous=degraded,
    )
    assert still_down["last_good"]["content_id"] == observed["content_id"]
    assert still_down["last_good"]["counts"] == observed["counts"]

    # A recovered reading may not silently regress its knowledge clock.
    with pytest.raises(ValueError, match="clock cannot regress"):
        build_idv_bridge_payload(
            idv_payload=build_idv_dossier_payload(
                tmp_path,
                prime_award_key_by_generated_id={CHILD: CHILD_AWARD_KEY},
                as_of="2026-08-02",
            ),
            prime_payload=_prime_payload(CHILD),
            as_of="2026-08-02",
            previous={
                **observed,
                "clocks": {**observed["clocks"], "known_at": "2030-01-01T00:00:00+00:00"},
                "content_id": idv_bridge_content_id(
                    {
                        **observed,
                        "clocks": {**observed["clocks"], "known_at": "2030-01-01T00:00:00+00:00"},
                    }
                ),
            },
        )


def test_gate_candidate_impact_stays_off(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    payload = _bridge(tmp_path, CHILD, PARENT)

    queue_authority = json.loads(
        (Path(__file__).parents[1] / "data" / "government_revenue" / "candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )["authority"]
    assert AUTHORITY == queue_authority == IDV_AUTHORITY
    assert payload["authority"] == queue_authority
    assert payload["authority"]["can_add_candidates"] is False
    assert payload["authority"]["can_escalate"] is False

    # No candidate family, ranking, or scoring FIELD exists anywhere in the rail;
    # the only permitted mention of candidates is the authority block's veto.
    def keys(value: Any) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for item in value.values() for key in keys(item)}
        if isinstance(value, list):
            return {key for item in value for key in keys(item)}
        return set()

    # The authority block IS the veto, so it is the only place those words appear.
    outside_authority = keys({key: item for key, item in payload.items() if key != "authority"})
    assert not any("candidate" in key for key in outside_authority)
    for forbidden in ("score", "rank", "weight", "signal", "prophet", "escalat", "gate"):
        assert not any(forbidden in key for key in outside_authority)
    assert keys(payload["authority"]) == set(queue_authority)
    assert "grc1-" not in json.dumps(payload) and "grcq1-" not in json.dumps(payload)
    source = (Path(__file__).parents[1] / "engine" / "government_revenue" / "idv_bridge.py").read_text(
        encoding="utf-8"
    )
    # The projector cannot reach the candidate rail at all: it imports neither
    # the candidate engine nor its queue artifact.
    assert "from engine.government_revenue.candidates" not in source
    assert "candidate_queue" not in source
    assert "candidate_ledger" not in source

    # Promoting authority in the artifact fails the contract.
    promoted = json.loads(json.dumps(payload))
    promoted["authority"]["can_add_candidates"] = True
    promoted["content_id"] = idv_bridge_content_id(promoted)
    assert not is_valid_idv_bridge_payload(promoted)


# --- Honesty, contract, and validator behaviour -----------------------------


def test_zero_bridges_are_reported_in_plain_words(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    payload = _bridge(tmp_path, "CONT_AWD_UNRELATED_3030_-NONE-_-NONE-")

    assert payload["status"] == "observed"
    assert payload["counts"]["bridged"] == 0
    assert "reported zero, not a hidden gap" in payload["disclosure"]
    assert any("not evidence that no relationship exists" in line for line in payload["limitations"])
    view = award_bridge_view(payload, "generated:CONT_AWD_UNRELATED_3030_-NONE-_-NONE-")
    assert view["status"] == "no_exact_link"
    assert "reported zero" in view["disclosure"]
    assert view["bridges"] == []
    assert view["total"] == 0

    # An observed generation that hides its zero instead of reporting it fails.
    silent = json.loads(json.dumps(payload))
    silent["disclosure"] = "No relationships."
    silent["content_id"] = idv_bridge_content_id(silent)
    assert not is_valid_idv_bridge_payload(silent)


def test_payload_satisfies_the_published_contract(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    payload = _bridge(tmp_path, CHILD, PARENT)
    schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert sorted(BRIDGE_STATES) == sorted(schema["$defs"]["bridge"]["properties"]["state"]["enum"])


def test_validator_rejects_a_forged_state_pairing(tmp_path: Path) -> None:
    """Each forgery is re-sealed, so only the semantic rule can catch it."""
    _write_bundle(tmp_path)
    payload = _bridge(tmp_path, CHILD)
    assert is_valid_idv_bridge_payload(_reseal(_forge(payload)))  # the harness itself is sound

    # A task order relabelled as a vehicle seat is exactly the prohibited claim.
    seat = _forge(payload)
    seat["bridges"][0]["state"] = "vehicle_membership"
    seat["bridges"][0]["evidence"]["basis"] = "prime_award_record_is_the_vehicle"
    seat["counts"]["vehicle_membership"] = 1
    seat["counts"]["task_order"] = 0
    assert not is_valid_idv_bridge_payload(_reseal(seat))

    # An enumerated link may not shed the receipt that proves it.
    unreceipted = _forge(payload)
    unreceipted["bridges"][0]["evidence"]["receipt_id"] = None
    unreceipted["bridges"][0]["evidence"]["response_sha256"] = None
    assert not is_valid_idv_bridge_payload(_reseal(unreceipted))

    # A count-only reading may not acquire an award key.
    _write_bundle(tmp_path, high_count_only=True)
    seated = _forge(_bridge(tmp_path, CHILD))
    seated["bridges"][0]["award_key"] = CHILD_AWARD_KEY
    seated["counts"]["count_only"] = 1
    assert not is_valid_idv_bridge_payload(_reseal(seated))


def test_validator_re_derives_a_tuple_link_from_its_own_identity(tmp_path: Path) -> None:
    """A composite-identity link must still decompose to the vehicle it claims."""
    _write_bundle(tmp_path, high_count_only=True)
    payload = _bridge(tmp_path, TUPLE_CHILD)
    row_index = next(
        index
        for index, row in enumerate(payload["bridges"])
        if row["evidence"]["basis"] == "source_native_parent_tuple"
    )

    swapped = _forge(payload)
    # An award whose own identity names a DIFFERENT vehicle cannot be attached here.
    swapped["bridges"][row_index]["identity"]["bridged_generated_award_id"] = (
        "CONT_AWD_TUPLEORDER_1010_OTHERPARENT_1010"
    )
    assert not is_valid_idv_bridge_payload(_reseal(swapped))

    # Nor can one whose identity names no vehicle at all.
    orphan = _forge(payload)
    orphan["bridges"][row_index]["identity"]["bridged_generated_award_id"] = (
        "CONT_AWD_TUPLEORDER_1010_-NONE-_-NONE-"
    )
    assert not is_valid_idv_bridge_payload(_reseal(orphan))


def test_bridge_rejects_a_foreign_or_unbound_source_payload(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    idv = build_idv_dossier_payload(
        tmp_path,
        prime_award_key_by_generated_id={CHILD: CHILD_AWARD_KEY},
        as_of="2026-08-02",
    )
    assert idv["contract"] == IDV_DOSSIER_CONTRACT

    with pytest.raises(ValueError, match="prime award dossier contract"):
        build_idv_bridge_payload(idv_payload=idv, prime_payload={"contract": "other.v1"}, as_of="2026-08-02")
    with pytest.raises(ValueError, match="IDV dossier contract"):
        build_idv_bridge_payload(
            idv_payload={"contract": "other.v1"}, prime_payload=_prime_payload(CHILD), as_of="2026-08-02"
        )
    with pytest.raises(ValueError, match="both source content identities"):
        build_idv_bridge_payload(
            idv_payload={**idv, "content_id": None},
            prime_payload=_prime_payload(CHILD),
            as_of="2026-08-02",
        )
    with pytest.raises(ValueError, match="previous IDV bridge generation identity"):
        build_idv_bridge_payload(
            idv_payload=idv,
            prime_payload=_prime_payload(CHILD),
            as_of="2026-08-02",
            previous={"contract": IDV_BRIDGE_CONTRACT, "content_id": "gribr1-" + "0" * 24},
        )


def test_award_route_publishes_the_bridge_without_the_raw_selection_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import government_revenue as api

    _write_bundle(tmp_path)
    idv = build_idv_dossier_payload(
        tmp_path,
        prime_award_key_by_generated_id={CHILD: CHILD_AWARD_KEY},
        as_of="2026-08-02",
    )
    prime = _prime_payload(CHILD)
    monkeypatch.setattr(api, "_load_dossiers", lambda: prime)
    monkeypatch.setattr(api, "_load_idv_dossiers", lambda: idv)
    api._IDV_BRIDGE_CACHE.update(state=None, payload=None)

    result = api.award_idv_relationships(CHILD_AWARD_KEY)

    bridge = result["bridge"]
    assert bridge["status"] == "bridged"
    assert bridge["total"] == 1
    assert bridge["bridges"][0]["state"] == "task_order"
    assert bridge["counts"]["bridged"] == 1
    assert bridge["collection_universe"]["selected_parent_count"] == 1
    # Wave 8 keeps the raw selection-manifest field out of the request contract;
    # each published link still names its own vehicle instead.
    assert "selected_parent_ids" not in json.dumps(result)
    assert bridge["bridges"][0]["identity"]["idv_generated_award_id"] == PARENT


def test_award_route_states_an_unprojectable_bridge_instead_of_hiding_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import government_revenue as api

    prime = {"content_id": "grd1-" + "a" * 24, "awards": [{"award_key": CHILD_AWARD_KEY, "identity": {}}]}
    monkeypatch.setattr(api, "_load_dossiers", lambda: prime)
    monkeypatch.setattr(api, "_load_idv_dossiers", lambda: {"relationships": [], "idvs": []})
    api._IDV_BRIDGE_CACHE.update(state=None, payload=None)

    bridge = api.award_idv_relationships(CHILD_AWARD_KEY)["bridge"]

    assert bridge["status"] == "unavailable"
    assert bridge["bridges"] == []
    assert bridge["counts"] is None
    assert "not an observation that no link exists" in bridge["disclosure"]
    assert bridge["authority"] == AUTHORITY


def test_grandchild_depth_is_preserved_not_flattened(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    payload = _bridge(tmp_path, GRANDCHILD)

    row = next(row for row in payload["bridges"] if row["state"] == "task_order")
    assert row["identity"]["bridged_generated_award_id"] == GRANDCHILD
    assert row["identity"]["relationship_depth"] == "grandchild_award"
    assert is_valid_idv_bridge_payload(payload)
