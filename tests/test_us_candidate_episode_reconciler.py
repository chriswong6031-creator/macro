"""B1 Task 3 — nightly-only candidate-episode reconciliation and publication."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import shutil

import pandas as pd
import pytest

from engine.us_candidate_episode import EpisodeContractError, canonical_json, load_all_candidates
from scripts import reconcile_us_candidate_episodes as writer


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "us_candidate_episode" / "intake"
RECORDED_AT = "2026-11-27T18:05:00Z"


def _snapshot(root: Path) -> dict[str, bytes | None]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


def _seed_sources(repo_root: Path) -> None:
    data = repo_root / "data"
    reference = data / "reference"
    reference.mkdir(parents=True)
    security_rows = json.loads((FIXTURE_ROOT / "security_master.json").read_text())
    alias_rows = json.loads((FIXTURE_ROOT / "vendor_aliases.json").read_text())
    pd.DataFrame(security_rows).to_parquet(reference / "security_master.parquet", index=False)
    pd.DataFrame(alias_rows).to_parquet(reference / "vendor_aliases.parquet", index=False)
    turn = data / "us_prophet_rank" / "episode_inputs" / "turn_watch" / "2026-11-27.json"
    turn.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURE_ROOT / "turn_watch.json", turn)


def _rehash_turn_watch(document: dict[str, object]) -> dict[str, object]:
    material = {key: value for key, value in document.items() if key != "content_sha256"}
    document["content_sha256"] = sha256(canonical_json(material).encode("utf-8")).hexdigest()
    return document


def _turn_path(repo_root: Path) -> Path:
    return repo_root / "data" / "us_prophet_rank" / "episode_inputs" / "turn_watch" / "2026-11-27.json"


def _run_nightly(repo_root: Path, monkeypatch, *, correction_path: Path | None = None) -> dict[str, object]:
    monkeypatch.setattr(writer, "nightly_advance_enabled", lambda: True)
    return writer.reconcile(
        repo_root=repo_root,
        nightly=True,
        replay=False,
        recorded_at=RECORDED_AT,
        correction_path=correction_path,
    )


def _episode_root(repo_root: Path) -> Path:
    return repo_root / "data" / "us_prophet_rank" / "episodes"


def _event_rows(repo_root: Path) -> list[dict[str, object]]:
    paths = sorted((_episode_root(repo_root) / "events").glob("*.jsonl"))
    return [json.loads(line) for path in paths for line in path.read_text().splitlines() if line]


def _parquet_logical_rows(path: Path) -> list[dict[str, object]]:
    rows = pd.read_parquet(path).to_dict("records")
    nested = {"intake_classes", "structural_anchor", "expert_events", "source_event_ids"}
    result: list[dict[str, object]] = []
    for row in rows:
        result.append({
            key: json.loads(value) if key in nested and isinstance(value, str) else value
            for key, value in row.items()
        })
    return result


def test_durable_gate_refuses_before_any_source_or_ledger_read(tmp_path: Path, monkeypatch):
    """Moving the lane check below a reader would let an off-lane write inspect truth."""
    monkeypatch.setattr(writer, "nightly_advance_enabled", lambda: False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("reader ran before the durable lane gate")

    for name in (
        "load_identity_spine",
        "turn_watch_observations",
        "candidate_observations",
        "door_observations",
        "radar_observations",
        "_load_existing_ledgers",
    ):
        monkeypatch.setattr(writer, name, forbidden)

    with pytest.raises(writer.ReconcileRefused, match="nightly_advance_enabled"):
        writer.reconcile(
            repo_root=tmp_path,
            nightly=True,
            replay=False,
            recorded_at=RECORDED_AT,
            correction_path=None,
        )
    assert _snapshot(tmp_path) == {}


def test_report_and_replay_modes_never_publish_or_change_the_tree(tmp_path: Path, monkeypatch):
    """Removing either read-only branch would let a non-nightly invocation write."""
    _seed_sources(tmp_path)
    before = _snapshot(tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("read-only mode reached transaction publication")

    monkeypatch.setattr(writer, "_publish_transaction", forbidden)
    report = writer.reconcile(
        repo_root=tmp_path,
        nightly=False,
        replay=False,
        recorded_at=RECORDED_AT,
        correction_path=None,
    )
    replay = writer.reconcile(
        repo_root=tmp_path,
        nightly=True,
        replay=True,
        recorded_at=RECORDED_AT,
        correction_path=None,
    )

    assert report["durable_write"] is False
    assert replay["durable_write"] is False
    assert report["mode"] == "report"
    assert replay["mode"] == "replay"
    assert _snapshot(tmp_path) == before


def test_natural_nightly_opens_once_and_publishes_exact_derived_targets(tmp_path: Path, monkeypatch):
    """Removing the canonical open or a projection target breaks the one-writer contract."""
    _seed_sources(tmp_path)
    receipt = _run_nightly(tmp_path, monkeypatch)
    episode_root = _episode_root(tmp_path)

    events = _event_rows(tmp_path)
    assert [event["event_type"] for event in events] == ["OPENED"]
    assert (episode_root / "events" / "2026-11.jsonl").read_bytes().endswith(b"\n")
    assert receipt["schema"] == "prophet.candidate_episode_reconcile_receipt/v1"
    assert receipt["mode"] == "nightly"
    assert receipt["gate"] == {"nightly_requested": True, "nightly_advance_enabled": True}
    assert receipt["durable_write"] is True
    assert receipt["definition_era"] == "candidate-episode-v1-2026-08-25"
    assert receipt["counts"] == {
        "input": 1,
        "mapped": 1,
        "suppressed": 0,
        "old_events": 0,
        "new_events": 1,
        "appended_events": 1,
    }
    assert receipt["source_counts"] == {
        "candidate": {"input": 0, "mapped": 0, "suppressed": 0},
        "doors": {"input": 0, "mapped": 0, "suppressed": 0},
        "entry_radar": {"input": 0, "mapped": 0, "suppressed": 0},
        "turn_watch": {"input": 1, "mapped": 1, "suppressed": 0},
    }
    assert set(receipt["projection_hashes"]) == {"all_candidates.json", "current.parquet"}
    assert all(str(value).startswith("sha256:") for value in receipt["source_hashes"].values())
    assert (episode_root / "latest_receipt.json").read_text() == canonical_json(receipt) + "\n"
    logical_json = load_all_candidates(episode_root / "all_candidates.json")
    logical_parquet = _parquet_logical_rows(episode_root / "current.parquet")
    assert logical_parquet == logical_json
    assert len(logical_json) == 1


def test_identical_nightly_is_content_addressed_and_rewrites_zero_bytes(tmp_path: Path, monkeypatch):
    """Using run time or old-count drift in a receipt would make a no-op rewrite bytes."""
    _seed_sources(tmp_path)
    first = _run_nightly(tmp_path, monkeypatch)
    before = _snapshot(tmp_path)
    second = _run_nightly(tmp_path, monkeypatch)

    assert second == first
    assert _snapshot(tmp_path) == before
    assert len(_event_rows(tmp_path)) == 1


def test_changed_observation_appends_observed_to_the_active_episode(tmp_path: Path, monkeypatch):
    """Re-opening on a changed source row would fork one active security lifecycle."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")

    receipt = _run_nightly(tmp_path, monkeypatch)
    events = _event_rows(tmp_path)
    assert sorted(event["event_type"] for event in events) == ["OBSERVED", "OPENED"]
    assert events == sorted(
        events,
        key=lambda row: (row["known_at"], row["source_system"], row["source_event_id"]),
    )
    assert len({event["episode_id"] for event in events}) == 1
    assert receipt["counts"]["appended_events"] == 1


def test_explicit_correction_appends_without_mutating_the_original_line(tmp_path: Path, monkeypatch):
    """Last-write-wins replacement would erase the immutable event being corrected."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    event_path = _episode_root(tmp_path) / "events" / "2026-11.jsonl"
    original_line = event_path.read_bytes()
    opened = _event_rows(tmp_path)[0]
    correction = tmp_path / "corrections.jsonl"
    command = {
        "event_type": "CORRECTED",
        "episode_id": opened["episode_id"],
        "source_system": "operator_correction",
        "source_schema": "prophet.candidate_episode_correction/v1",
        "source_event_id": "correction-1",
        "occurred_at": RECORDED_AT,
        "known_at": RECORDED_AT,
        "source_receipt": "sha256:" + "a" * 64,
        "correction_of": opened["event_id"],
        "payload": {"patch": {"ticker_at_observation": "ALFA.C"}},
    }
    correction.write_text(canonical_json(command) + "\n")

    _run_nightly(tmp_path, monkeypatch, correction_path=correction)
    assert event_path.read_bytes().startswith(original_line)
    assert [event["event_type"] for event in _event_rows(tmp_path)] == ["OPENED", "CORRECTED"]
    assert load_all_candidates(_episode_root(tmp_path) / "all_candidates.json")[0][
        "ticker_at_observation"
    ] == "ALFA.C"


def test_staging_validation_failure_leaves_the_complete_prior_tree(tmp_path: Path, monkeypatch):
    """Publishing before staged validation would expose an unverified target subset."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    before = _snapshot(tmp_path)
    monkeypatch.setattr(writer, "_validate_staged", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("injected staged validation failure")
    ))

    with pytest.raises(RuntimeError, match="injected staged validation failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert _snapshot(tmp_path) == before


def test_replace_failure_rolls_back_every_changed_target(tmp_path: Path, monkeypatch):
    """Losing rollback after one replace would split ledger from its projections."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    before = _snapshot(tmp_path)
    real_replace = writer._replace_file
    calls = 0

    def fail_once(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected replace failure")
        real_replace(source, target)

    monkeypatch.setattr(writer, "_replace_file", fail_once)
    with pytest.raises(OSError, match="injected replace failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert _snapshot(tmp_path) == before


def test_corrupt_existing_event_hash_aborts_before_every_output(tmp_path: Path, monkeypatch):
    """Skipping validation of old truth would let corruption flow into every projection."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    event_path = _episode_root(tmp_path) / "events" / "2026-11.jsonl"
    row = json.loads(event_path.read_text())
    row["content_sha256"] = "0" * 64
    event_path.write_text(canonical_json(row) + "\n")
    before = _snapshot(tmp_path)

    with pytest.raises(EpisodeContractError, match="content address or bytes"):
        _run_nightly(tmp_path, monkeypatch)
    assert _snapshot(tmp_path) == before


def test_monthly_ledgers_are_canonical_sorted_jsonl_and_suppressions_are_truth(tmp_path: Path, monkeypatch):
    """Unsorted or non-addressed rows would make replay bytes depend on source iteration."""
    _seed_sources(tmp_path)
    document = json.loads(_turn_path(tmp_path).read_text())
    unknown = json.loads(canonical_json(document["rows"][0]))
    unknown["ticker"] = "UNKNOWN"
    document["rows"].append(unknown)
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    receipt = _run_nightly(tmp_path, monkeypatch)

    event_lines = (_episode_root(tmp_path) / "events" / "2026-11.jsonl").read_text().splitlines()
    suppression_lines = (
        _episode_root(tmp_path) / "suppressions" / "2026-11.jsonl"
    ).read_text().splitlines()
    events = [json.loads(line) for line in event_lines]
    suppressions = [json.loads(line) for line in suppression_lines]
    assert event_lines == [canonical_json(row) for row in events]
    assert suppression_lines == [canonical_json(row) for row in suppressions]
    assert events == sorted(events, key=lambda row: (row["known_at"], row["source_system"], row["source_event_id"]))
    assert suppressions == sorted(suppressions, key=lambda row: row["suppression_id"])
    assert receipt["counts"]["input"] == receipt["counts"]["mapped"] + receipt["counts"]["suppressed"]
    assert receipt["counts"]["suppressed"] == 1
    assert all(
        counts["input"] == counts["mapped"] + counts["suppressed"]
        for counts in receipt["source_counts"].values()
    )


def test_uncapped_input_accounting_preserves_every_logical_candidate(tmp_path: Path, monkeypatch):
    """A producer cap or silent drop would make input differ from mapped plus suppressed."""
    data = tmp_path / "data"
    reference = data / "reference"
    reference.mkdir(parents=True)
    count = 305
    securities = []
    aliases = []
    rows = []
    for index in range(count):
        ticker = f"X{index:03d}"
        security = f"SEC:US-XNAS-{ticker}"
        issuer = f"ISS:US-XNAS-{ticker}"
        securities.append({"security_id": security, "issuer_id": issuer, "issuer_state": "ACTIVE", "listing_key": f"US-XNAS-{ticker}"})
        aliases.append({"vendor": "membership", "vendor_symbol": ticker, "security_id": security, "valid_from": "2020-01-01", "valid_to": None})
        rows.append({
            "ticker": ticker,
            "asof": "2026-11-27",
            "triggers": {"dot_1d": {"fired": True, "evaluated": True, "last_date": "2026-11-27"}},
            "reset": {"reset_low": 10 + index / 10, "reset_low_date": "2026-11-27"},
        })
    pd.DataFrame(securities).to_parquet(reference / "security_master.parquet", index=False)
    pd.DataFrame(aliases).to_parquet(reference / "vendor_aliases.parquet", index=False)
    turn = {
        "schema": "prophet.candidate_episode_input.turn_watch/v1",
        "data_session": "2026-11-27",
        "known_at": "2026-11-27T18:00:00Z",
        "selection_era": "anticipation-v1",
        "anchor_era": "anchor-v1",
        "source_artifact_sha256": "sha256:" + "2" * 64,
        "rows": rows,
    }
    path = _turn_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(canonical_json(_rehash_turn_watch(turn)) + "\n")

    receipt = _run_nightly(tmp_path, monkeypatch)
    projected = load_all_candidates(_episode_root(tmp_path) / "all_candidates.json")
    assert receipt["counts"]["input"] == count
    assert receipt["counts"]["mapped"] == count
    assert receipt["counts"]["suppressed"] == 0
    assert len(projected) == count


def test_downstream_fixture_consumes_only_the_canonical_reader(tmp_path: Path, monkeypatch):
    """A downstream parquet read would bypass the sole All Candidates contract reader."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    monkeypatch.setattr(pd, "read_parquet", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("downstream bypassed load_all_candidates")
    ))

    def downstream_fixture(path: Path) -> list[str]:
        return [row["episode_id"] for row in load_all_candidates(path)]

    assert downstream_fixture(_episode_root(tmp_path) / "all_candidates.json")
