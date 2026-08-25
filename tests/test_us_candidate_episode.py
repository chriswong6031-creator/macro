"""Contract tests for the pure ``prophet.candidate_episode/v1`` core."""
from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from engine.stock_identity import fingerprint
from engine.us_candidate_episode import (
    EpisodeContractError,
    anchor_token,
    apply_commands,
    build_all_candidates,
    canonical_anchor,
    canonical_json,
    episode_id,
    load_all_candidates,
    make_event,
    project_events,
    reconcile_observations,
    validate_events,
)


SECURITY_ID = "SEC:US-XNAS-XYZ"
COMPANY_ID = "ISS:US-XNAS-XYZ"
ERA = "candidate-episode-v1-2026-08-25"
RECORDED_AT = "2026-08-25T02:00:00Z"
ANCHOR = {
    "kind": "turn_watch_reset_low",
    "time": "2026-08-24T20:00:00Z",
    "price": 42.1,
    "basis": "adjusted_close",
    "source_receipt": "sha256:receipt-a",
}


def _observation(*, source_event_id: str = "turn-watch:XYZ:2026-08-24", anchor=ANCHOR, **extra):
    value = {
        "security_id": SECURITY_ID,
        "company_id": COMPANY_ID,
        "ticker_at_observation": "XYZ",
        "identity_epoch": "epoch_0",
        "identity_epoch_state": "provisional",
        "identity_spec_schema": "stock_identity.fingerprint_spec.v1",
        "identity_spec_hash": fingerprint.spec_hash(),
        "anchor": anchor,
        "intake_class": "technical_emergence",
        "occurred_at": "2026-08-24T20:00:00Z",
        "known_at": "2026-08-24T20:00:00Z",
        "source_system": "turn_watch",
        "source_schema": "turn_watch.candidate_input/v1",
        "source_event_id": source_event_id,
        "source_receipt": "sha256:turn-watch-input",
    }
    value.update(extra)
    return value


def _event(event_type: str, episode: str, *, payload: dict, source_event_id: str, correction_of=None):
    return make_event(
        event_type=event_type,
        episode_id=episode,
        source_system="test_source",
        source_schema="test.source/v1",
        source_event_id=source_event_id,
        occurred_at="2026-08-24T20:00:00Z",
        known_at="2026-08-24T20:00:00Z",
        recorded_at=RECORDED_AT,
        source_receipt="sha256:test-source",
        definition_era=ERA,
        correction_of=correction_of,
        payload=payload,
    )


def test_canonical_anchor_ignores_receipt_but_preserves_exact_anchor_identity():
    assert canonical_json({"b": 1, "a": None}) == '{"a":null,"b":1}'
    assert anchor_token(ANCHOR) == anchor_token({**ANCHOR, "source_receipt": "sha256:receipt-b"})
    assert canonical_anchor(ANCHOR) == {
        "kind": "turn_watch_reset_low",
        "time": "2026-08-24T20:00:00Z",
        "price": "42.1",
        "basis": "adjusted_close",
    }
    assert episode_id(SECURITY_ID, "epoch_0", ANCHOR, 1).startswith(
        "pe:SEC:US-XNAS-XYZ:epoch_0:sa:"
    )


@pytest.mark.parametrize(
    ("security_id", "identity_epoch", "anchor", "generation"),
    [
        ("sec:US-XNAS-XYZ", "epoch_0", ANCHOR, 1),
        (SECURITY_ID, "", ANCHOR, 1),
        (SECURITY_ID, "epoch_0", {"kind": "turn_watch_reset_low"}, 1),
        (SECURITY_ID, "epoch_0", {**ANCHOR, "time": "2026-08-24T20:00:00"}, 1),
        (SECURITY_ID, "epoch_0", {**ANCHOR, "price": float("nan")}, 1),
        (SECURITY_ID, "epoch_0", ANCHOR, 0),
    ],
)
def test_episode_identity_rejects_invalid_contract_values(security_id, identity_epoch, anchor, generation):
    with pytest.raises(EpisodeContractError):
        episode_id(security_id, identity_epoch, anchor, generation)


def test_event_validation_rejects_unknown_types_bad_ids_and_illegal_clocks():
    episode = episode_id(SECURITY_ID, "epoch_0", ANCHOR, 1)
    event = _event("OBSERVED", episode, payload={"intake_class": "technical_emergence"}, source_event_id="1")
    assert validate_events([event]) == [event]

    for mutation in (
        {"event_type": "UNKNOWN"},
        {"episode_id": "pe:bad"},
        {"known_at": "2026-08-25T03:00:00Z"},
        {"occurred_at": "2026-08-24T20:00:00"},
    ):
        invalid = copy.deepcopy(event)
        invalid.update(mutation)
        invalid.pop("content_sha256", None)
        with pytest.raises(EpisodeContractError):
            validate_events([invalid])


def test_reconciliation_opens_and_idempotently_observes_one_episode():
    first = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    assert len(first.new_events) == 1
    assert first.episodes[0]["episode_id"] == episode_id(SECURITY_ID, "epoch_0", ANCHOR, 1)
    assert first.episodes[0]["company_id"] == COMPANY_ID
    assert first.episodes[0]["identity_epoch_state"] == "provisional"
    assert first.episodes[0]["structural_anchor"]["source_receipt"] == "sha256:receipt-a"

    repeat = _observation(source_event_id="turn-watch:XYZ:2026-08-25")
    second = reconcile_observations(first.events, [repeat], recorded_at=RECORDED_AT, definition_era=ERA)
    assert [event["event_type"] for event in second.new_events] == ["OBSERVED"]
    rerun = reconcile_observations(second.events, [repeat], recorded_at=RECORDED_AT, definition_era=ERA)
    assert rerun.new_events == ()
    assert canonical_json(rerun.episodes) == canonical_json(second.episodes)


def test_reconciliation_deduplicates_a_repeated_source_input_and_rejects_bad_issuer():
    observation = _observation()
    result = reconcile_observations(
        [], [observation, observation], recorded_at=RECORDED_AT, definition_era=ERA
    )
    assert [event["event_type"] for event in result.events] == ["OPENED"]
    rerun = reconcile_observations(
        result.events, [observation], recorded_at=RECORDED_AT, definition_era=ERA
    )
    assert rerun.new_events == ()
    with pytest.raises(EpisodeContractError):
        reconcile_observations(
            [], [{**observation, "company_id": "ISS"}], recorded_at=RECORDED_AT, definition_era=ERA
        )


def test_expert_events_use_exact_radar_event_id_and_unanchored_input_needs_active_episode():
    expert = _observation(
        anchor=None,
        source_event_id="radar:event:content-addressed-1",
        source_system="entry_radar",
        source_schema="mastermind.entry_event.v1",
        expert_event_id="radar:event:content-addressed-1",
        intake_class="radar_expert",
    )
    suppressed = reconcile_observations([], [expert], recorded_at=RECORDED_AT, definition_era=ERA)
    assert suppressed.events == ()
    assert suppressed.suppressions[0]["reason"] == "MISSING_STRUCTURAL_ANCHOR"

    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    attached = reconcile_observations(opened.events, [expert], recorded_at=RECORDED_AT, definition_era=ERA)
    row = attached.episodes[0]
    assert row["expert_events"] == ["radar:event:content-addressed-1"]
    assert attached.new_events[0]["payload"]["expert_event_id"] == "radar:event:content-addressed-1"


def test_active_different_anchor_is_suppressed_and_terminal_rearm_opens_next_generation():
    first = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    new_anchor = {**ANCHOR, "time": "2026-08-25T20:00:00Z", "price": "43.2"}
    blocked = reconcile_observations(
        first.events,
        [_observation(source_event_id="turn-watch:XYZ:alternate", anchor=new_anchor)],
        recorded_at=RECORDED_AT,
        definition_era=ERA,
    )
    assert blocked.new_events == ()
    assert blocked.suppressions[0]["reason"] == "ACTIVE_EPISODE_DIFFERENT_ANCHOR"

    old_id = first.episodes[0]["episode_id"]
    resolved = _event(
        "STATE_TRANSITIONED",
        old_id,
        source_event_id="state:resolved",
        payload={"episode_state": "RESOLVED", "terminal_reason": "expired"},
    )
    rearmed = reconcile_observations(
        [*first.events, resolved],
        [_observation(source_event_id="turn-watch:XYZ:rearm", anchor=new_anchor)],
        recorded_at=RECORDED_AT,
        definition_era=ERA,
    )
    assert len(rearmed.episodes) == 2
    assert rearmed.episodes[1]["episode_id"].endswith(":2")
    assert rearmed.episodes[1]["rearm_of"] == old_id
    assert [row["episode_state"] for row in rearmed.episodes] == ["RESOLVED", "ACTIVE"]


def test_projection_corrections_retractions_and_supersession_append_immutable_events():
    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    episode = opened.episodes[0]["episode_id"]
    observed = _event(
        "OBSERVED", episode, source_event_id="candidate:1", payload={"intake_class": "technical_emergence"}
    )
    commands = [
        {
            "event_type": "CORRECTED",
            "episode_id": episode,
            "source_system": "operator",
            "source_schema": "candidate-command/v1",
            "source_event_id": "correct:1",
            "source_receipt": "sha256:operator",
            "occurred_at": "2026-08-24T20:00:00Z",
            "known_at": "2026-08-24T20:00:00Z",
            "correction_of": observed["event_id"],
            "payload": {"patch": {"ticker_at_observation": "XYZZ"}},
        },
        {
            "event_type": "RETRACTED",
            "episode_id": episode,
            "source_system": "operator",
            "source_schema": "candidate-command/v1",
            "source_event_id": "retract:1",
            "source_receipt": "sha256:operator",
            "occurred_at": "2026-08-24T20:00:00Z",
            "known_at": "2026-08-24T20:00:00Z",
            "correction_of": observed["event_id"],
            "payload": {"reason": "source withdrew observation"},
        },
        {
            "event_type": "IDENTITY_SUPERSEDED",
            "episode_id": episode,
            "source_system": "stock_identity",
            "source_schema": "stock_identity.epoch/v1",
            "source_event_id": "identity:1",
            "source_receipt": "sha256:identity",
            "occurred_at": "2026-08-24T20:00:00Z",
            "known_at": "2026-08-24T20:00:00Z",
            "payload": {"successor_episode_id": episode_id(SECURITY_ID, "epoch_1", ANCHOR, 1), "reason": "epoch detected"},
        },
    ]
    result = apply_commands([*opened.events, observed], commands, recorded_at=RECORDED_AT, definition_era=ERA)
    assert result.episodes[0]["ticker_at_observation"] == "XYZZ"
    assert result.episodes[0]["correction_state"] == "corrected"
    assert result.episodes[0]["observation_count"] == 0
    assert result.episodes[0]["superseded_by"] == episode_id(SECURITY_ID, "epoch_1", ANCHOR, 1)
    assert observed in result.events

    invalid = copy.deepcopy(commands[0])
    invalid["correction_of"] = "pee:missing"
    with pytest.raises(EpisodeContractError):
        apply_commands(opened.events, [invalid], recorded_at=RECORDED_AT, definition_era=ERA)


def test_projection_rejects_two_active_episodes_for_one_security_epoch():
    episode_1 = episode_id(SECURITY_ID, "epoch_0", ANCHOR, 1)
    second_anchor = {**ANCHOR, "time": "2026-08-25T20:00:00Z"}
    episode_2 = episode_id(SECURITY_ID, "epoch_0", second_anchor, 2)
    opened_1 = _event("OPENED", episode_1, source_event_id="open:1", payload={**_observation(), "anchor": ANCHOR})
    opened_2 = _event("OPENED", episode_2, source_event_id="open:2", payload={**_observation(anchor=second_anchor), "anchor": second_anchor})
    with pytest.raises(EpisodeContractError, match="two active"):
        project_events([opened_1, opened_2])


def test_all_candidates_is_uncapped_and_loader_uses_canonical_fixture(tmp_path: Path):
    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    terminal = _event(
        "STATE_TRANSITIONED",
        opened.episodes[0]["episode_id"],
        source_event_id="state:resolved",
        payload={"episode_state": "RESOLVED", "terminal_reason": "expired"},
    )
    document = build_all_candidates([*opened.events, terminal], suppression_count=7)
    assert document["coverage"] == {"episodes": 1, "active": 0, "suppressed_inputs": 7}
    assert document["episodes"][0]["episode_state"] == "RESOLVED"

    fixture = Path(__file__).parent / "fixtures/us_candidate_episode/all_candidates.json"
    rows = load_all_candidates(fixture)
    assert [row["episode_id"] for row in rows] == sorted(row["episode_id"] for row in rows)
    duplicate = json.loads(fixture.read_text())
    duplicate["episodes"].append(copy.deepcopy(duplicate["episodes"][0]))
    duplicate_path = tmp_path / "duplicate.json"
    duplicate_path.write_text(json.dumps(duplicate))
    with pytest.raises(EpisodeContractError, match="duplicate"):
        load_all_candidates(duplicate_path)


def test_replay_and_ledger_hash_use_known_at_source_system_source_event_id_order():
    """Changing source ordering, rather than a hash, changes canonical ledger order."""
    first_anchor = {**ANCHOR, "time": "2026-08-24T19:00:00Z"}
    second_anchor = {**ANCHOR, "time": "2026-08-24T19:30:00Z"}
    first = _event(
        "OPENED",
        episode_id("SEC:US-XNAS-AAA", "epoch_0", first_anchor, 1),
        source_event_id="z-event",
        payload={**_observation(anchor=first_anchor, security_id="SEC:US-XNAS-AAA", company_id="ISS:US-XNAS-AAA", ticker_at_observation="AAA"), "structural_anchor": first_anchor},
    )
    second = _event(
        "OPENED",
        episode_id("SEC:US-XNAS-BBB", "epoch_0", second_anchor, 1),
        source_event_id="a-event",
        payload={**_observation(anchor=second_anchor, security_id="SEC:US-XNAS-BBB", company_id="ISS:US-XNAS-BBB", ticker_at_observation="BBB"), "structural_anchor": second_anchor},
    )
    # Deliberately choose source systems whose declared order differs from event hashes.
    first["source_system"] = "z_source"
    second["source_system"] = "a_source"
    for event in (first, second):
        semantic = {key: event[key] for key in ("event_type", "episode_id", "source_system", "source_schema", "source_event_id", "occurred_at", "known_at", "definition_era", "correction_of", "payload")}
        event["event_id"] = "pee:" + sha256(canonical_json(semantic).encode()).hexdigest()
        event["content_sha256"] = sha256(canonical_json({key: value for key, value in event.items() if key != "content_sha256"}).encode()).hexdigest()
    document = build_all_candidates([first, second], suppression_count=0)
    expected = [second, first]
    assert document["generated_from"]["ledger_sha256"] == "sha256:" + sha256(canonical_json(expected).encode()).hexdigest()


def test_data_os_identity_and_epoch_zero_stock_identity_provenance_fail_closed():
    with pytest.raises(EpisodeContractError):
        episode_id("SEC::", "epoch_0", ANCHOR, 1)
    with pytest.raises(EpisodeContractError):
        reconcile_observations(
            [], [_observation(company_id="ISS::")], recorded_at=RECORDED_AT, definition_era=ERA
        )
    with pytest.raises(EpisodeContractError, match="Stock Identity"):
        reconcile_observations(
            [], [_observation(identity_spec_hash="not-the-live-spec-hash")], recorded_at=RECORDED_AT, definition_era=ERA
        )


def test_expert_attachment_requires_exact_radar_contract_and_keeps_two_events_on_one_episode():
    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    foreign = _observation(
        anchor=None,
        source_system="not_radar",
        source_schema="not.mastermind.entry_event",
        source_event_id="radar:event:foreign",
        expert_event_id="radar:event:foreign",
    )
    with pytest.raises(EpisodeContractError, match="Radar"):
        reconcile_observations(opened.events, [foreign], recorded_at=RECORDED_AT, definition_era=ERA)
    experts = [
        _observation(
            anchor=None,
            source_system="entry_radar",
            source_schema="mastermind.entry_event.v1",
            source_event_id=f"radar:event:{ordinal}",
            expert_event_id=f"radar:event:{ordinal}",
            intake_class="radar_expert",
        )
        for ordinal in ("one", "two")
    ]
    attached = reconcile_observations(opened.events, experts, recorded_at=RECORDED_AT, definition_era=ERA)
    assert len(attached.episodes) == 1
    assert attached.episodes[0]["expert_events"] == ["radar:event:one", "radar:event:two"]


def test_replay_rejects_unknown_and_terminal_to_active_same_generation_transitions():
    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    episode = opened.episodes[0]["episode_id"]
    resolved = _event("STATE_TRANSITIONED", episode, source_event_id="state:resolved", payload={"episode_state": "RESOLVED", "terminal_reason": "expired"})
    active = _event("STATE_TRANSITIONED", episode, source_event_id="state:active", payload={"episode_state": "ACTIVE"})
    unknown = _event("STATE_TRANSITIONED", episode, source_event_id="state:unknown", payload={"episode_state": "MAYBE"})
    with pytest.raises(EpisodeContractError, match="terminal"):
        project_events([*opened.events, resolved, active])
    with pytest.raises(EpisodeContractError, match="unknown episode state"):
        project_events([*opened.events, unknown])


def test_commands_validate_values_targets_and_identity_supersession_invariants():
    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    episode = opened.episodes[0]["episode_id"]
    transition = _event("STATE_TRANSITIONED", episode, source_event_id="state:resolved", payload={"episode_state": "RESOLVED", "terminal_reason": "expired"})
    correction = {
        "event_type": "CORRECTED", "episode_id": episode, "source_system": "operator",
        "source_schema": "candidate-command/v1", "source_event_id": "correct:transition",
        "source_receipt": "sha256:operator", "occurred_at": "2026-08-24T20:00:00Z",
        "known_at": "2026-08-24T20:00:00Z", "correction_of": transition["event_id"],
        "payload": {"patch": {"terminal_reason": "reclassified"}},
    }
    assert apply_commands([*opened.events, transition], [correction], recorded_at=RECORDED_AT, definition_era=ERA).episodes[0]["terminal_reason"] == "reclassified"

    invalid_patch = copy.deepcopy(correction)
    invalid_patch["source_event_id"] = "correct:invalid-company"
    invalid_patch["payload"] = {"patch": {"company_id": "ISS::"}}
    with pytest.raises(EpisodeContractError, match="company_id"):
        apply_commands([*opened.events, transition], [invalid_patch], recorded_at=RECORDED_AT, definition_era=ERA)

    forbidden_patch = copy.deepcopy(correction)
    forbidden_patch["source_event_id"] = "correct:immutable-anchor"
    forbidden_patch["payload"] = {"patch": {"structural_anchor": {"kind": "replacement"}}}
    with pytest.raises(EpisodeContractError, match="immutable"):
        apply_commands([*opened.events, transition], [forbidden_patch], recorded_at=RECORDED_AT, definition_era=ERA)

    other = episode_id("SEC:US-XNAS-OTHER", "epoch_0", ANCHOR, 1)
    cross_retraction = {
        "event_type": "RETRACTED", "episode_id": other, "source_system": "operator",
        "source_schema": "candidate-command/v1", "source_event_id": "retract:cross",
        "source_receipt": "sha256:operator", "occurred_at": "2026-08-24T20:00:00Z",
        "known_at": "2026-08-24T20:00:00Z", "correction_of": transition["event_id"],
        "payload": {"reason": "wrong episode"},
    }
    with pytest.raises(EpisodeContractError, match="retraction episode"):
        apply_commands([*opened.events, transition], [cross_retraction], recorded_at=RECORDED_AT, definition_era=ERA)

    missing_reason = copy.deepcopy(cross_retraction)
    missing_reason["episode_id"] = episode
    missing_reason["source_event_id"] = "retract:missing-reason"
    missing_reason["payload"] = {}
    with pytest.raises(EpisodeContractError, match="reason"):
        apply_commands([*opened.events, transition], [missing_reason], recorded_at=RECORDED_AT, definition_era=ERA)

    missing_receipt = copy.deepcopy(correction)
    missing_receipt["source_event_id"] = "correct:missing-receipt"
    missing_receipt["source_receipt"] = ""
    with pytest.raises(EpisodeContractError, match="source_receipt"):
        apply_commands([*opened.events, transition], [missing_receipt], recorded_at=RECORDED_AT, definition_era=ERA)

    for source_provenance in ("provisional", "confirmed"):
        if source_provenance == "provisional":
            source = opened.events
            source_episode = episode
            successor = episode
        else:
            alternate = reconcile_observations(
                [], [_observation(identity_epoch="epoch_1", identity_epoch_state="confirmed")],
                recorded_at=RECORDED_AT, definition_era=ERA,
            )
            source = alternate.events
            source_episode = alternate.episodes[0]["episode_id"]
            successor = episode_id(SECURITY_ID, "epoch_2", ANCHOR, 1)
        supersession = {
            "event_type": "IDENTITY_SUPERSEDED", "episode_id": source_episode, "source_system": "stock_identity",
            "source_schema": "stock_identity.epoch/v1", "source_event_id": f"identity:{source_provenance}:{successor}",
            "source_receipt": "sha256:identity", "occurred_at": "2026-08-24T20:00:00Z",
            "known_at": "2026-08-24T20:00:00Z", "payload": {"successor_episode_id": successor, "reason": "epoch detected"},
        }
        with pytest.raises(EpisodeContractError, match="supersession"):
            apply_commands(source, [supersession], recorded_at=RECORDED_AT, definition_era=ERA)


def test_all_candidates_reader_verifies_identity_id_provenance_and_canonical_order(tmp_path: Path):
    fixture = Path(__file__).parent / "fixtures/us_candidate_episode/all_candidates.json"
    document = json.loads(fixture.read_text())
    for mutation in (
        lambda value: value.update({"schema": "wrong"}),
        lambda value: value.update({"definition_era": "wrong"}),
        lambda value: value["episodes"][0].update({"security_id": "SEC::"}),
        lambda value: value["episodes"][0].update({"identity_spec_hash": "wrong"}),
        lambda value: value["episodes"][0].update({"identity_epoch_state": "confirmed"}),
        lambda value: value["episodes"][0].update({"episode_id": "pe:SEC:US-XNAS-AAA:epoch_0:sa:wrong:1"}),
        lambda value: value["episodes"][0]["structural_anchor"].update({"source_receipt": "placeholder"}),
        lambda value: value["generated_from"].update({"ledger_sha256": "sha256:fixture"}),
        lambda value: value.update({"episodes": list(reversed(value["episodes"]))}),
    ):
        invalid = copy.deepcopy(document)
        mutation(invalid)
        path = tmp_path / f"invalid-{len(list(tmp_path.iterdir()))}.json"
        path.write_text(json.dumps(invalid))
        with pytest.raises(EpisodeContractError):
            load_all_candidates(path)


def test_all_candidates_projection_is_not_capped_at_a_small_episode_count():
    observations = [
        _observation(
            source_event_id=f"turn-watch:scale:{index}", security_id=f"SEC:US-XNAS-X{index:03d}",
            company_id=f"ISS:US-XNAS-X{index:03d}", ticker_at_observation=f"X{index:03d}",
        )
        for index in range(300)
    ]
    result = reconcile_observations([], observations, recorded_at=RECORDED_AT, definition_era=ERA)
    document = build_all_candidates(result.events, suppression_count=0)
    assert document["coverage"]["episodes"] == 300
    assert len(document["episodes"]) == 300


def test_data_os_identity_uses_its_canonical_parser_for_dotted_and_reused_listings(tmp_path: Path):
    dotted_security = "SEC:US-XNYS-BRK.B"
    dotted_issuer = "ISS:US-XNYS-BRK.B"
    reused_security = "SEC:US-XNYS-MMC.2"
    assert episode_id(dotted_security, "epoch_0", ANCHOR, 1).startswith(f"pe:{dotted_security}:")
    assert episode_id(reused_security, "epoch_0", ANCHOR, 1).startswith(f"pe:{reused_security}:")
    opened = reconcile_observations(
        [], [_observation(security_id=dotted_security, company_id=dotted_issuer, ticker_at_observation="BRK.B")],
        recorded_at=RECORDED_AT, definition_era=ERA,
    )
    assert opened.episodes[0]["security_id"] == dotted_security

    for bad_security, bad_issuer in (("SEC:US-ZZZZ-ABC", COMPANY_ID), (SECURITY_ID, "ISS:US")):
        with pytest.raises(EpisodeContractError):
            reconcile_observations(
                [], [_observation(security_id=bad_security, company_id=bad_issuer)],
                recorded_at=RECORDED_AT, definition_era=ERA,
            )

    document = json.loads((Path(__file__).parent / "fixtures/us_candidate_episode/all_candidates.json").read_text())
    row = document["episodes"][0]
    row["security_id"] = dotted_security
    row["company_id"] = dotted_issuer
    row["episode_id"] = episode_id(dotted_security, row["identity_epoch"], row["structural_anchor"], 1)
    path = tmp_path / "dotted.json"
    path.write_text(json.dumps(document))
    assert load_all_candidates(path)[0]["security_id"] == dotted_security


def test_retractions_fail_closed_for_effects_without_a_deterministic_inverse():
    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    episode = opened.episodes[0]["episode_id"]
    state = _event(
        "STATE_TRANSITIONED", episode, source_event_id="state:resolved",
        payload={"episode_state": "RESOLVED", "terminal_reason": "expired"},
    )
    correction = _event(
        "CORRECTED", episode, source_event_id="correct:state", correction_of=state["event_id"],
        payload={"patch": {"terminal_reason": "reclassified"}},
    )
    supersession = _event(
        "IDENTITY_SUPERSEDED", episode, source_event_id="identity:successor",
        payload={"successor_episode_id": episode_id(SECURITY_ID, "epoch_1", ANCHOR, 1), "reason": "epoch detected"},
    )
    for target in (state, correction, supersession):
        retraction = _event(
            "RETRACTED", episode, source_event_id=f"retract:{target['event_type']}",
            correction_of=target["event_id"], payload={"reason": "must not become a no-op"},
        )
        with pytest.raises(EpisodeContractError, match="unsupported retraction target"):
            project_events([*opened.events, state, correction, supersession, retraction])


def test_correction_cannot_leave_a_terminal_episode_without_its_terminal_reason():
    opened = reconcile_observations([], [_observation()], recorded_at=RECORDED_AT, definition_era=ERA)
    episode = opened.episodes[0]["episode_id"]
    state = _event(
        "STATE_TRANSITIONED", episode, source_event_id="state:resolved",
        payload={"episode_state": "RESOLVED", "terminal_reason": "expired"},
    )
    invalid = {
        "event_type": "CORRECTED", "episode_id": episode, "source_system": "operator",
        "source_schema": "candidate-command/v1", "source_event_id": "correct:terminal-reason-none",
        "source_receipt": "sha256:operator", "occurred_at": "2026-08-24T20:00:00Z",
        "known_at": "2026-08-24T20:00:00Z", "correction_of": state["event_id"],
        "payload": {"patch": {"terminal_reason": None}},
    }
    with pytest.raises(EpisodeContractError, match="terminal_reason"):
        apply_commands([*opened.events, state], [invalid], recorded_at=RECORDED_AT, definition_era=ERA)
