"""B1 Task 2 — canonical candidate-episode intake boundaries."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine.stock_identity.fingerprint import spec_hash
from engine.us_candidate_episode import reconcile_observations
from engine.us_candidate_episode_intake import (
    candidate_observations,
    door_observations,
    load_identity_spine,
    radar_observations,
    turn_watch_observations,
)
from scripts.build_turn_watch import write_candidate_episode_input


def _identity_spine(root: Path, *, issuer: str | None = "ISS:US-XNAS-ALFA") -> None:
    reference = root / "reference"
    reference.mkdir(parents=True)
    pd.DataFrame([{
        "security_id": "SEC:US-XNAS-ALFA", "issuer_id": issuer,
        "issuer_state": "ACTIVE", "listing_key": "US-XNAS-ALFA",
    }]).to_parquet(reference / "security_master.parquet", index=False)
    pd.DataFrame([{
        "vendor": "membership", "vendor_symbol": "ALFA",
        "security_id": "SEC:US-XNAS-ALFA", "valid_from": date(2020, 1, 1),
        "valid_to": None,
    }]).to_parquet(reference / "vendor_aliases.parquet", index=False)


def _turn_artifact() -> dict:
    return {
        "schema": "us_turn_watch.v1", "data_session": "2026-11-27",
        "selection_era": "anticipation-v1", "anchor_era": "anchor-v1",
        "triggers": {"dot_1d": {"en": "Daily turn dot"}},
    }


def _turn_row(**overrides) -> dict:
    row = {
        "ticker": "ALFA", "asof": "2026-11-27", "triggers_fired": ["dot_1d"],
        "triggers": {"dot_1d": {"fired": True, "evaluated": True,
                                 "last_date": "2026-11-27"}},
        "reset": {"reset_low": 42.1, "reset_low_date": "2026-11-27"},
    }
    row.update(overrides)
    return row


def _ids(batch) -> set[str]:
    return {str(row["source_event_id"]) for row in batch.observations} | {
        str(row["source_event_id"]) for row in batch.suppressions
    }


def test_turn_watch_sidecar_and_identity_spine_open_at_the_nyse_early_close(tmp_path: Path):
    """Changing the session clock or bypassing Data OS identity breaks this contract."""
    data = tmp_path / "data"
    _identity_spine(data)
    out = write_candidate_episode_input(_turn_artifact(), [_turn_row()], data)
    document = json.loads(out.read_text())
    assert out == data / "us_prophet_rank" / "episode_inputs" / "turn_watch" / "2026-11-27.json"
    assert document["schema"] == "prophet.candidate_episode_input.turn_watch/v1"
    assert document["known_at"] == "2026-11-27T18:00:00Z"  # Thanksgiving Friday, 13:00 ET.
    assert len(document["rows"]) == 1
    assert document["content_sha256"]

    batch = turn_watch_observations(out, load_identity_spine(data))
    assert len(batch.observations) == 1
    observed = batch.observations[0]
    assert observed["security_id"] == "SEC:US-XNAS-ALFA"
    assert observed["company_id"] == "ISS:US-XNAS-ALFA"
    assert observed["identity_epoch"] == "epoch_0"
    assert observed["identity_epoch_state"] == "provisional"
    assert observed["identity_spec_schema"] == "stock_identity.fingerprint_spec.v1"
    assert observed["identity_spec_hash"] == spec_hash()
    assert observed["anchor"]["time"] == "2026-11-27T18:00:00Z"
    result = reconcile_observations([], batch.observations,
                                    recorded_at="2026-11-27T18:00:00Z",
                                    definition_era="candidate-episode-v1-2026-08-25")
    assert result.episodes[0]["opened_at"] == "2026-11-27T18:00:00Z"


@pytest.mark.parametrize(
    ("row", "issuer", "reason"),
    [
        (_turn_row(triggers={"dot_1d": {"fired": True, "evaluated": False}}),
         "ISS:US-XNAS-ALFA", "UNEVALUATED_TRIGGER"),
        (_turn_row(reset={"reset_low": None, "reset_low_date": None}),
         "ISS:US-XNAS-ALFA", "MISSING_RESET_LOW"),
        (_turn_row(ticker="UNKNOWN"), "ISS:US-XNAS-ALFA", "IDENTITY_UNRESOLVED"),
        (_turn_row(), None, "ISSUER_UNRESOLVED"),
    ],
)
def test_turn_watch_invalid_structural_inputs_suppress_once(tmp_path: Path, row: dict,
                                                            issuer: str | None, reason: str):
    data = tmp_path / "data"
    _identity_spine(data, issuer=issuer)
    path = write_candidate_episode_input(_turn_artifact(), [row], data)
    batch = turn_watch_observations(path, load_identity_spine(data))
    assert batch.observations == ()
    assert [entry["reason"] for entry in batch.suppressions] == [reason]
    assert _ids(batch) == {batch.suppressions[0]["source_event_id"]}


def test_turn_watch_content_hash_mismatch_is_a_per_row_malformed_receipt(tmp_path: Path):
    data = tmp_path / "data"
    _identity_spine(data)
    path = write_candidate_episode_input(_turn_artifact(), [_turn_row()], data)
    document = json.loads(path.read_text())
    document["rows"][0]["ticker"] = "TAMPERED"
    path.write_text(json.dumps(document))
    batch = turn_watch_observations(path, load_identity_spine(data))
    assert batch.observations == ()
    assert [entry["reason"] for entry in batch.suppressions] == ["MALFORMED_RECEIPT"]


def test_non_anchor_sources_attach_or_suppress_and_preserve_exact_radar_event_id(tmp_path: Path):
    """Only TURN WATCH may open; all other rows retain one unambiguous disposition."""
    data = tmp_path / "data"
    _identity_spine(data)
    spine = load_identity_spine(data)
    candidates = data / "us_prophet_rank" / "candidates"
    candidates.mkdir(parents=True)
    pd.DataFrame([{"ticker": "ALFA", "as_of": "2026-11-27"}]).to_parquet(
        candidates / "2026-11.parquet", index=False)
    doors = data / "prophet_doors" / "flags.jsonl"
    doors.parent.mkdir(parents=True)
    doors.write_text(json.dumps({"schema": "prophet_doors/v1", "date": "2026-11-27",
                                 "door": "T", "ticker": "ALFA", "features": {}}) + "\n")
    radar = data / "entry_radar" / "forward.parquet"
    radar.parent.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "ALFA", "event_id": "radar-expert-17",
        "signal_ts": "2026-11-27T18:00:00Z", "signal_known_ts": "2026-11-27T18:00:00Z",
    }]).to_parquet(radar, index=False)

    candidate_batch = candidate_observations(data, spine)
    door_batch = door_observations(doors, spine)
    radar_batch = radar_observations(radar, spine)
    assert len(candidate_batch.observations) == len(door_batch.observations) == 1
    assert candidate_batch.observations[0]["anchor"] is None
    assert door_batch.observations[0]["anchor"] is None
    assert radar_batch.observations[0]["source_event_id"] == "radar-expert-17"
    assert radar_batch.observations[0]["expert_event_id"] == "radar-expert-17"
    assert radar_batch.observations[0]["anchor"] is None
    assert reconcile_observations([], [*candidate_batch.observations, *door_batch.observations,
                                       *radar_batch.observations],
                                  recorded_at="2026-11-27T18:00:00Z",
                                  definition_era="candidate-episode-v1-2026-08-25").suppressions
    assert _ids(candidate_batch) == {candidate_batch.observations[0]["source_event_id"]}
    assert _ids(door_batch) == {door_batch.observations[0]["source_event_id"]}
    assert _ids(radar_batch) == {"radar-expert-17"}


def test_missing_optional_source_is_named_degraded_receipt(tmp_path: Path):
    data = tmp_path / "data"
    _identity_spine(data)
    batch = candidate_observations(data, load_identity_spine(data))
    assert batch.observations == batch.suppressions == ()
    assert batch.source_receipts == ({"source": "candidate", "status": "degraded",
                                      "reason": "MISSING_SOURCE_FILE"},)
