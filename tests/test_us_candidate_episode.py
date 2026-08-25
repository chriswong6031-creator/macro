"""Contract tests for the pure ``prophet.candidate_episode/v1`` core."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

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
COMPANY_ID = "ISS:US-XYZ"
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
        "identity_spec_hash": "sha256:stock-identity-spec",
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
        source_event_id="radar:source:1",
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
            "payload": {"successor_episode_id": "pe:SEC:US-XNAS-XYZ:epoch_1:sa:successor:1", "reason": "epoch detected"},
        },
    ]
    result = apply_commands([*opened.events, observed], commands, recorded_at=RECORDED_AT, definition_era=ERA)
    assert result.episodes[0]["ticker_at_observation"] == "XYZZ"
    assert result.episodes[0]["correction_state"] == "corrected"
    assert result.episodes[0]["observation_count"] == 0
    assert result.episodes[0]["superseded_by"] == "pe:SEC:US-XNAS-XYZ:epoch_1:sa:successor:1"
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
