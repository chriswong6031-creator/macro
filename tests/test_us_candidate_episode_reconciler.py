"""B1 Task 3 — nightly-only candidate-episode reconciliation and publication."""
from __future__ import annotations

import json
from hashlib import sha256
import importlib.util
from pathlib import Path
import shutil

import pandas as pd
import pytest

from engine.us_candidate_episode import (
    EpisodeContractError,
    canonical_json,
    load_all_candidates,
    load_candidate_episode_store,
)
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


def _run_nightly(
    repo_root: Path,
    monkeypatch,
    *,
    correction_path: Path | None = None,
    recorded_at: str = RECORDED_AT,
) -> dict[str, object]:
    monkeypatch.setattr(writer, "nightly_advance_enabled", lambda: True)
    return writer.reconcile(
        repo_root=repo_root,
        nightly=True,
        replay=False,
        recorded_at=recorded_at,
        correction_path=correction_path,
    )


def _episode_root(repo_root: Path) -> Path:
    return repo_root / "data" / "us_prophet_rank" / "episodes"


def _head(repo_root: Path) -> dict[str, object]:
    return json.loads((_episode_root(repo_root) / "HEAD.json").read_text())


def _generation(repo_root: Path) -> Path:
    return _episode_root(repo_root) / "generations" / str(_head(repo_root)["generation_id"])


def _readdress_current_generation(repo_root: Path) -> Path:
    """Forge a self-consistent manifest/HEAD around deliberately changed generation bytes."""
    generation = _generation(repo_root)
    files: dict[str, dict[str, object]] = {}
    for path in sorted(generation.rglob("*")):
        relative = str(path.relative_to(generation))
        if not path.is_file() or relative == "manifest.json":
            continue
        payload = path.read_bytes()
        files[relative] = {
            "sha256": "sha256:" + sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    material = {
        "schema": "prophet.candidate_episode_generation_manifest/v1",
        "files": files,
    }
    generation_id = "peg:" + sha256(canonical_json(material).encode("utf-8")).hexdigest()
    manifest = {**material, "generation_id": generation_id}
    manifest["content_sha256"] = sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
    manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
    (generation / "manifest.json").write_bytes(manifest_bytes)
    destination = generation.parent / generation_id
    generation.rename(destination)
    head = {
        "schema": "prophet.candidate_episode_head/v1",
        "generation_id": generation_id,
        "manifest_sha256": "sha256:" + sha256(manifest_bytes).hexdigest(),
    }
    head["content_sha256"] = sha256(canonical_json(head).encode("utf-8")).hexdigest()
    (_episode_root(repo_root) / "HEAD.json").write_text(canonical_json(head) + "\n")
    return destination


def _event_rows(repo_root: Path) -> list[dict[str, object]]:
    paths = sorted((_generation(repo_root) / "events").glob("*.jsonl"))
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
    generation = _generation(tmp_path)

    events = _event_rows(tmp_path)
    assert [event["event_type"] for event in events] == ["OPENED"]
    assert (generation / "events" / "2026-11.jsonl").read_bytes().endswith(b"\n")
    assert _head(tmp_path)["schema"] == "prophet.candidate_episode_head/v1"
    assert str(_head(tmp_path)["generation_id"]).startswith("peg:")
    assert (generation / "manifest.json").is_file()
    assert receipt["schema"] == "prophet.candidate_episode_reconcile_receipt/v1"
    assert receipt["mode"] == "nightly"
    assert receipt["gate"] == {"nightly_requested": True, "nightly_advance_enabled": True}
    assert receipt["durable_write"] is True
    assert receipt["definition_era"] == "candidate-episode-v1-2026-08-25"
    assert receipt["counts"] == {
        "input": 1,
        "mapped": 1,
        "suppressed": 0,
        "ledger_suppressions": 0,
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
    assert (generation / "latest_receipt.json").read_text() == canonical_json(receipt) + "\n"
    logical_json = load_all_candidates(generation / "all_candidates.json")
    logical_parquet = _parquet_logical_rows(generation / "current.parquet")
    assert logical_parquet == logical_json
    assert load_candidate_episode_store(episode_root) == logical_json
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


def test_suppression_retry_at_later_recorded_at_retains_original_immutable_row(
    tmp_path: Path, monkeypatch,
):
    """The writer clock is not the semantic identity of an at-least-once suppression."""
    _seed_sources(tmp_path)
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["ticker"] = "UNKNOWN"
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    first = _run_nightly(tmp_path, monkeypatch)
    before = _snapshot(tmp_path)
    first_row = json.loads(next((_generation(tmp_path) / "suppressions").glob("*.jsonl")).read_text())

    second = _run_nightly(
        tmp_path, monkeypatch, recorded_at="2026-11-27T18:06:00Z",
    )

    assert second == first
    assert _snapshot(tmp_path) == before
    row = json.loads(next((_generation(tmp_path) / "suppressions").glob("*.jsonl")).read_text())
    assert row == first_row
    assert row["recorded_at"] == RECORDED_AT


def test_first_publication_has_no_current_generation_until_head_swap(tmp_path: Path, monkeypatch):
    """A generation directory alone must never become the canonical read target."""
    _seed_sources(tmp_path)
    monkeypatch.setattr(writer, "_publish_head", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("stop before first HEAD")
    ))

    with pytest.raises(RuntimeError, match="before first HEAD"):
        _run_nightly(tmp_path, monkeypatch)
    assert not (_episode_root(tmp_path) / "HEAD.json").exists()
    assert len(list((_episode_root(tmp_path) / "generations").iterdir())) == 1
    with pytest.raises(EpisodeContractError, match="HEAD"):
        load_candidate_episode_store(_episode_root(tmp_path))


def test_first_publication_fsyncs_new_store_parent_before_head_replace(tmp_path: Path, monkeypatch):
    """Omitting the store parent's fsync can lose the new episodes directory after success."""
    _seed_sources(tmp_path)
    parent = tmp_path / "data" / "us_prophet_rank"
    fsynced: list[Path] = []
    real_fsync = writer._fsync_directory
    real_replace = writer._replace_head

    def record_fsync(path: Path) -> None:
        fsynced.append(Path(path))
        real_fsync(path)

    def replace_after_parent_fsync(source: Path, target: Path) -> None:
        assert parent in fsynced
        real_replace(source, target)

    monkeypatch.setattr(writer, "_fsync_directory", record_fsync)
    monkeypatch.setattr(writer, "_replace_head", replace_after_parent_fsync)
    _run_nightly(tmp_path, monkeypatch)

    assert load_candidate_episode_store(_episode_root(tmp_path))


def test_first_publication_parent_fsync_failure_never_publishes_head(tmp_path: Path, monkeypatch):
    """A failed durability fence must abort before the sole visibility boundary."""
    _seed_sources(tmp_path)
    parent = tmp_path / "data" / "us_prophet_rank"
    real_fsync = writer._fsync_directory

    def fail_store_parent(path: Path) -> None:
        if Path(path) == parent:
            raise OSError("injected episodes parent fsync failure")
        real_fsync(path)

    monkeypatch.setattr(writer, "_fsync_directory", fail_store_parent)
    with pytest.raises(OSError, match="episodes parent fsync failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert not (_episode_root(tmp_path) / "HEAD.json").exists()


def test_retry_after_failed_first_parent_fsync_fences_episodes_before_head(
    tmp_path: Path, monkeypatch,
):
    """Filesystem existence cannot stand in for retrying a failed parent durability fence."""
    _seed_sources(tmp_path)
    episode_root = _episode_root(tmp_path)
    parent = episode_root.parent
    real_fsync = writer._fsync_directory

    def fail_first_parent_fsync(path: Path) -> None:
        if Path(path) == parent:
            raise OSError("injected first episodes parent fsync failure")
        real_fsync(path)

    monkeypatch.setattr(writer, "_fsync_directory", fail_first_parent_fsync)
    with pytest.raises(OSError, match="first episodes parent fsync failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert episode_root.is_dir()
    assert not (episode_root / "HEAD.json").exists()

    retry_parent_fsyncs = 0
    real_replace = writer._replace_head

    def record_retry_fsync(path: Path) -> None:
        nonlocal retry_parent_fsyncs
        if Path(path) == parent:
            retry_parent_fsyncs += 1
        real_fsync(path)

    def replace_after_retry_fence(source: Path, target: Path) -> None:
        assert retry_parent_fsyncs >= 1
        real_replace(source, target)

    monkeypatch.setattr(writer, "_fsync_directory", record_retry_fsync)
    monkeypatch.setattr(writer, "_replace_head", replace_after_retry_fence)
    receipt = _run_nightly(tmp_path, monkeypatch)

    assert retry_parent_fsyncs >= 1
    assert receipt["durable_write"] is True
    assert load_candidate_episode_store(episode_root)


def test_reader_observes_only_old_or_new_generation_across_one_head_replace(tmp_path: Path, monkeypatch):
    """Any multi-file visibility boundary would expose a mixed ledger/projection set here."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    old_rows = load_candidate_episode_store(_episode_root(tmp_path))
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    real_publish = writer._publish_head
    observed: list[list[dict[str, object]]] = []

    def observe_swap(*args, **kwargs):
        observed.append(load_candidate_episode_store(_episode_root(tmp_path)))
        result = real_publish(*args, **kwargs)
        observed.append(load_candidate_episode_store(_episode_root(tmp_path)))
        return result

    monkeypatch.setattr(writer, "_publish_head", observe_swap)
    _run_nightly(tmp_path, monkeypatch)
    new_rows = load_candidate_episode_store(_episode_root(tmp_path))
    assert observed == [old_rows, new_rows]
    assert old_rows[0]["observation_count"] == 0
    assert new_rows[0]["observation_count"] == 1


def test_existing_store_uses_the_same_validated_head_snapshot_it_opened(tmp_path: Path, monkeypatch):
    """Reopening HEAD after validation can select a concurrent, unvalidated generation."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    head_path = _episode_root(tmp_path) / "HEAD.json"
    head_a = head_path.read_bytes()
    generation_a = str(json.loads(head_a)["generation_id"])

    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    _run_nightly(tmp_path, monkeypatch)
    head_b = head_path.read_text()
    head_path.write_bytes(head_a)
    real_read_text = Path.read_text

    def concurrent_head_text(path: Path, *args, **kwargs):
        if path == head_path:
            return head_b
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", concurrent_head_text)
    loaded = writer._load_existing_ledgers(_episode_root(tmp_path))

    assert loaded[2] == _episode_root(tmp_path) / "generations" / generation_a
    assert len(loaded[0]) == 1


def test_failure_during_atomic_head_replace_keeps_old_generation_current(tmp_path: Path, monkeypatch):
    """A failed pointer replace must not expose the already-installed orphan generation."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    old_head = (_episode_root(tmp_path) / "HEAD.json").read_bytes()
    old_rows = load_candidate_episode_store(_episode_root(tmp_path))
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    monkeypatch.setattr(writer, "_replace_head", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        OSError("injected HEAD replace failure")
    ))

    with pytest.raises(OSError, match="HEAD replace failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert (_episode_root(tmp_path) / "HEAD.json").read_bytes() == old_head
    assert load_candidate_episode_store(_episode_root(tmp_path)) == old_rows


def test_failure_before_head_temp_is_written_keeps_old_generation_current(tmp_path: Path, monkeypatch):
    """The pointer temp-file window is still before the single visibility boundary."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    old_head = (_episode_root(tmp_path) / "HEAD.json").read_bytes()
    old_rows = load_candidate_episode_store(_episode_root(tmp_path))
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    monkeypatch.setattr(writer.tempfile, "mkstemp", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        OSError("injected HEAD temp failure")
    ))

    with pytest.raises(OSError, match="HEAD temp failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert (_episode_root(tmp_path) / "HEAD.json").read_bytes() == old_head
    assert load_candidate_episode_store(_episode_root(tmp_path)) == old_rows


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
    event_path = _generation(tmp_path) / "events" / "2026-11.jsonl"
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
    corrected_event_path = _generation(tmp_path) / "events" / "2026-11.jsonl"
    assert corrected_event_path.read_bytes().startswith(original_line)
    assert [event["event_type"] for event in _event_rows(tmp_path)] == ["OPENED", "CORRECTED"]
    assert load_candidate_episode_store(_episode_root(tmp_path))[0][
        "ticker_at_observation"
    ] == "ALFA.C"


def test_correction_retry_at_later_recorded_time_reuses_original_generation_bytes(tmp_path: Path, monkeypatch):
    """At-least-once delivery must retain the original immutable correction envelope."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    opened = _event_rows(tmp_path)[0]
    correction = tmp_path / "corrections.jsonl"
    command = {
        "event_type": "CORRECTED",
        "episode_id": opened["episode_id"],
        "source_system": "operator_correction",
        "source_schema": "prophet.candidate_episode_correction/v1",
        "source_event_id": "retry-safe-correction",
        "occurred_at": RECORDED_AT,
        "known_at": RECORDED_AT,
        "source_receipt": "sha256:" + "b" * 64,
        "correction_of": opened["event_id"],
        "payload": {"patch": {"ticker_at_observation": "ALFA.R"}},
    }
    correction.write_text(canonical_json(command) + "\n")
    first = _run_nightly(tmp_path, monkeypatch, correction_path=correction)
    before = _snapshot(_episode_root(tmp_path))

    second = _run_nightly(
        tmp_path,
        monkeypatch,
        correction_path=correction,
        recorded_at="2026-11-27T18:06:00Z",
    )
    assert second == first
    assert _snapshot(_episode_root(tmp_path)) == before
    correction_events = [row for row in _event_rows(tmp_path) if row["event_type"] == "CORRECTED"]
    assert len(correction_events) == 1
    assert correction_events[0]["recorded_at"] == RECORDED_AT


def test_same_correction_source_identity_with_changed_payload_fails_closed(tmp_path: Path, monkeypatch):
    """Source-address reuse with changed semantics must not mint a second command effect."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    opened = _event_rows(tmp_path)[0]
    correction = tmp_path / "corrections.jsonl"
    command = {
        "event_type": "CORRECTED", "episode_id": opened["episode_id"],
        "source_system": "operator_correction",
        "source_schema": "prophet.candidate_episode_correction/v1",
        "source_event_id": "stable-command-address",
        "occurred_at": RECORDED_AT, "known_at": RECORDED_AT,
        "source_receipt": "sha256:" + "c" * 64,
        "correction_of": opened["event_id"],
        "payload": {"patch": {"ticker_at_observation": "ALFA.ONE"}},
    }
    correction.write_text(canonical_json(command) + "\n")
    _run_nightly(tmp_path, monkeypatch, correction_path=correction)
    command["payload"] = {"patch": {"ticker_at_observation": "ALFA.TWO"}}
    correction.write_text(canonical_json(command) + "\n")
    before = _snapshot(_episode_root(tmp_path))

    with pytest.raises(EpisodeContractError, match="source identity"):
        _run_nightly(tmp_path, monkeypatch, correction_path=correction,
                     recorded_at="2026-11-27T18:06:00Z")
    assert _snapshot(_episode_root(tmp_path)) == before


def test_failure_before_generation_install_leaves_old_head_canonical(tmp_path: Path, monkeypatch):
    """Installing unvalidated bytes would let HEAD expose an incomplete generation."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    old_head = (_episode_root(tmp_path) / "HEAD.json").read_bytes()
    old_rows = load_candidate_episode_store(_episode_root(tmp_path))
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    monkeypatch.setattr(writer, "_install_generation", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("injected generation install failure")
    ))

    with pytest.raises(RuntimeError, match="generation install failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert (_episode_root(tmp_path) / "HEAD.json").read_bytes() == old_head
    assert load_candidate_episode_store(_episode_root(tmp_path)) == old_rows


def test_installed_orphan_before_head_swap_is_not_reader_visible(tmp_path: Path, monkeypatch):
    """Selecting an unreferenced generation would bypass the sole visibility boundary."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    old_head = (_episode_root(tmp_path) / "HEAD.json").read_bytes()
    old_rows = load_candidate_episode_store(_episode_root(tmp_path))
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["observation_revision"] = 2
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    monkeypatch.setattr(writer, "_publish_head", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("injected pre-HEAD failure")
    ))
    with pytest.raises(RuntimeError, match="pre-HEAD failure"):
        _run_nightly(tmp_path, monkeypatch)
    assert (_episode_root(tmp_path) / "HEAD.json").read_bytes() == old_head
    assert load_candidate_episode_store(_episode_root(tmp_path)) == old_rows
    generations = list((_episode_root(tmp_path) / "generations").iterdir())
    assert len(generations) == 2  # complete orphan plus the still-canonical old generation.


def test_turn_watch_receipt_hashes_the_exact_once_read_bytes(tmp_path: Path, monkeypatch):
    """Reopening latest input after normalization could attest a different source snapshot."""
    _seed_sources(tmp_path)
    original = _turn_path(tmp_path).read_bytes()
    original_digest = "sha256:" + sha256(original).hexdigest()
    real_normalize = writer.turn_watch_observations

    def normalize_then_replace(path: Path, spine):
        batch = real_normalize(path, spine)
        replacement = json.loads(path.read_text())
        replacement["rows"][0]["ticker"] = "REPLACED_AFTER_READ"
        path.write_text(canonical_json(_rehash_turn_watch(replacement)) + "\n")
        return batch

    monkeypatch.setattr(writer, "turn_watch_observations", normalize_then_replace)
    receipt = _run_nightly(tmp_path, monkeypatch)
    turn_hashes = {
        path: digest for path, digest in receipt["source_hashes"].items()
        if "turn_watch" in path
    }
    assert turn_hashes == {
        "data/us_prophet_rank/episode_inputs/turn_watch/2026-11-27.json": original_digest,
    }
    assert load_candidate_episode_store(_episode_root(tmp_path))[0]["security_id"] == "SEC:US-XNAS-ALFA"


def test_source_status_files_share_canonical_paths_and_digests_with_source_hashes(
    tmp_path: Path, monkeypatch,
):
    """A readdressed receipt must not assert two digests for one disclosed source file."""
    _seed_sources(tmp_path)
    receipt = _run_nightly(tmp_path, monkeypatch)
    file_rows = [
        file_row
        for source_receipt in receipt["source_receipts"]
        for file_row in source_receipt.get("files", [])
    ]
    assert file_rows
    for file_row in file_rows:
        assert receipt["source_hashes"][file_row["path"]] == file_row["sha256"]

    generation = _generation(tmp_path)
    receipt_path = generation / "latest_receipt.json"
    forged = json.loads(receipt_path.read_text())
    turn_watch = next(
        source_receipt
        for source_receipt in forged["source_receipts"]
        if source_receipt["source"] == "turn_watch"
    )
    turn_watch["files"][0]["sha256"] = "sha256:" + "0" * 64
    receipt_path.write_text(canonical_json(forged) + "\n")
    _readdress_current_generation(tmp_path)

    with pytest.raises(EpisodeContractError, match="source file receipt.*source hash"):
        load_candidate_episode_store(_episode_root(tmp_path))


def test_correction_receipt_hashes_the_exact_once_read_bytes(tmp_path: Path, monkeypatch):
    """A correction re-read after parsing could bind the receipt to unexecuted bytes."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    opened = _event_rows(tmp_path)[0]
    correction = tmp_path / "commands.jsonl"
    command = {
        "event_type": "CORRECTED", "episode_id": opened["episode_id"],
        "source_system": "operator_correction",
        "source_schema": "prophet.candidate_episode_correction/v1",
        "source_event_id": "once-read-command", "occurred_at": RECORDED_AT,
        "known_at": RECORDED_AT, "source_receipt": "sha256:" + "d" * 64,
        "correction_of": opened["event_id"],
        "payload": {"patch": {"ticker_at_observation": "ALFA.ONCE"}},
    }
    correction.write_text(canonical_json(command) + "\n")
    original = correction.read_bytes()
    original_digest = "sha256:" + sha256(original).hexdigest()
    real_load = writer._load_commands_snapshot

    def load_then_replace(path: Path | None):
        result = real_load(path)
        assert path is not None
        path.write_text("{}\n")
        return result

    monkeypatch.setattr(writer, "_load_commands_snapshot", load_then_replace)
    receipt = _run_nightly(tmp_path, monkeypatch, correction_path=correction)
    assert receipt["source_hashes"]["commands.jsonl"] == original_digest
    assert load_candidate_episode_store(_episode_root(tmp_path))[0]["ticker_at_observation"] == "ALFA.ONCE"


@pytest.mark.parametrize("recorded_at", ["badZ", "2026-11-27T18:05:00+00:00", "2026-11-27", "2026-11-27T18:05:00.000000Z"])
def test_recorded_at_is_canonical_utc_before_any_ledger_or_source_read(
    tmp_path: Path, monkeypatch, recorded_at: str,
):
    """Zero-input publication must not bypass the persistence clock boundary."""
    monkeypatch.setattr(writer, "nightly_advance_enabled", lambda: True)
    monkeypatch.setattr(writer, "_load_existing_ledgers", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("ledger read before recorded_at validation")
    ))
    with pytest.raises(EpisodeContractError, match="recorded_at"):
        writer.reconcile(repo_root=tmp_path, nightly=True, replay=False,
                         recorded_at=recorded_at, correction_path=None)
    assert _snapshot(tmp_path) == {}


def test_default_recorded_at_is_validated_at_the_same_boundary(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(writer, "nightly_advance_enabled", lambda: True)
    monkeypatch.setattr(writer, "_now", lambda: "not-canonicalZ")
    monkeypatch.setattr(writer, "_load_existing_ledgers", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("ledger read before default recorded_at validation")
    ))
    with pytest.raises(EpisodeContractError, match="recorded_at"):
        writer.reconcile(repo_root=tmp_path, nightly=True, replay=False,
                         recorded_at=None, correction_path=None)


def test_corrupt_existing_event_hash_aborts_before_every_output(tmp_path: Path, monkeypatch):
    """Skipping validation of old truth would let corruption flow into every projection."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    event_path = _generation(tmp_path) / "events" / "2026-11.jsonl"
    row = json.loads(event_path.read_text())
    row["content_sha256"] = "0" * 64
    event_path.write_text(canonical_json(row) + "\n")
    before = _snapshot(tmp_path)

    with pytest.raises(EpisodeContractError, match="manifest file hash"):
        _run_nightly(tmp_path, monkeypatch)
    assert _snapshot(tmp_path) == before


def test_head_is_exact_content_addressed_and_rejects_unknown_fields(tmp_path: Path, monkeypatch):
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    head_path = _episode_root(tmp_path) / "HEAD.json"
    head = json.loads(head_path.read_text())
    head["unexpected"] = True
    head_path.write_text(canonical_json(head) + "\n")
    with pytest.raises(EpisodeContractError, match="HEAD"):
        load_candidate_episode_store(_episode_root(tmp_path))


def test_generation_manifest_rejects_extra_or_hash_changed_files(tmp_path: Path, monkeypatch):
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    generation = _generation(tmp_path)
    (generation / "unexpected.json").write_text("{}\n")
    with pytest.raises(EpisodeContractError, match="unexpected file"):
        load_candidate_episode_store(_episode_root(tmp_path))
    (generation / "unexpected.json").unlink()
    all_candidates = generation / "all_candidates.json"
    all_candidates.write_bytes(all_candidates.read_bytes() + b" ")
    with pytest.raises(EpisodeContractError, match="manifest"):
        load_candidate_episode_store(_episode_root(tmp_path))


def test_nested_manifest_named_file_is_not_exempt_from_exact_generation_membership(
    tmp_path: Path, monkeypatch,
):
    """Exempting by basename lets an unauthenticated nested file evade the generation address."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    generation = _generation(tmp_path)
    (generation / "events" / "manifest.json").write_text("{}\n")

    with pytest.raises(EpisodeContractError, match="unexpected file|file set"):
        load_candidate_episode_store(_episode_root(tmp_path))
    with pytest.raises(EpisodeContractError, match="unexpected file|content address"):
        writer._validate_generation_directory(generation, generation.name)


@pytest.mark.parametrize("target", ["parquet", "receipt"])
def test_canonical_reader_rejects_self_addressed_generation_with_cross_file_semantic_drift(
    tmp_path: Path, monkeypatch, target: str,
):
    """A manifest authenticates bytes; it cannot substitute for projection/receipt semantics."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    generation = _generation(tmp_path)
    if target == "parquet":
        pd.DataFrame([]).to_parquet(generation / "current.parquet", index=False)
    else:
        receipt_path = generation / "latest_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["counts"]["old_events"] += 1
        receipt_path.write_text(canonical_json(receipt) + "\n")
    _readdress_current_generation(tmp_path)

    with pytest.raises(EpisodeContractError, match="parquet|receipt"):
        load_candidate_episode_store(_episode_root(tmp_path))


def test_canonical_reader_rejects_projection_not_recomputed_from_immutable_events(
    tmp_path: Path, monkeypatch,
):
    """Projection bytes and their hashes cannot replace the immutable event ledger."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    generation = _generation(tmp_path)
    projection_path = generation / "all_candidates.json"
    projection = json.loads(projection_path.read_text())
    projection["episodes"][0]["ticker_at_observation"] = "ALFA.LEDGER-DRIFT"
    projection_bytes = (canonical_json(projection) + "\n").encode("utf-8")
    projection_path.write_bytes(projection_bytes)

    parquet_path = generation / "current.parquet"
    parquet_bytes = writer._parquet_bytes(projection["episodes"])
    parquet_path.write_bytes(parquet_bytes)

    receipt_path = generation / "latest_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["projection_hashes"] = {
        "all_candidates.json": "sha256:" + sha256(projection_bytes).hexdigest(),
        "current.parquet": "sha256:" + sha256(parquet_bytes).hexdigest(),
    }
    receipt_path.write_text(canonical_json(receipt) + "\n")
    _readdress_current_generation(tmp_path)

    with pytest.raises(EpisodeContractError, match="immutable event ledger projection"):
        load_candidate_episode_store(_episode_root(tmp_path))


def test_event_partition_loader_rejects_noncanonical_wrong_month_and_duplicate_rows(
    tmp_path: Path, monkeypatch,
):
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    row = _event_rows(tmp_path)[0]
    partitions = tmp_path / "partitions"
    partitions.mkdir()
    canonical = canonical_json(row) + "\n"

    (partitions / "2026-11.jsonl").write_text("  " + canonical)
    with pytest.raises(EpisodeContractError, match="canonical"):
        writer._load_event_partitions(partitions)
    (partitions / "2026-11.jsonl").unlink()

    (partitions / "2026-10.jsonl").write_text(canonical)
    with pytest.raises(EpisodeContractError, match="month"):
        writer._load_event_partitions(partitions)
    (partitions / "2026-10.jsonl").unlink()

    (partitions / "2026-11.jsonl").write_text(canonical + canonical)
    with pytest.raises(EpisodeContractError, match="duplicate"):
        writer._load_event_partitions(partitions)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: {**row, "extra": True},
        lambda row: {key: value for key, value in row.items() if key != "reason"},
        lambda row: {**row, "recorded_at": "not-a-clockZ"},
        lambda row: {**row, "reason": "UNKNOWN_REASON"},
        lambda row: {**row, "source_receipt": "not-a-receipt"},
    ],
)
def test_suppression_validation_requires_exact_closed_envelope(tmp_path: Path, monkeypatch, mutation):
    _seed_sources(tmp_path)
    document = json.loads(_turn_path(tmp_path).read_text())
    document["rows"][0]["ticker"] = "UNKNOWN"
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    _run_nightly(tmp_path, monkeypatch)
    suppression_path = next((_generation(tmp_path) / "suppressions").glob("*.jsonl"))
    row = json.loads(suppression_path.read_text())
    broken = mutation(row)
    material = {key: value for key, value in broken.items()
                if key not in {"suppression_id", "content_sha256", "recorded_at"}}
    broken["suppression_id"] = "pes:" + sha256(canonical_json(material).encode()).hexdigest()
    broken["content_sha256"] = sha256(canonical_json({
        key: value for key, value in broken.items() if key != "content_sha256"
    }).encode()).hexdigest()
    with pytest.raises(EpisodeContractError, match="suppression"):
        writer.validate_suppressions([broken])


@pytest.mark.parametrize(
    "target", ["receipt_ledger", "projection_count", "source_balance", "parquet", "extra_file"],
)
def test_staged_cross_target_validation_recomputes_every_declared_invariant(
    tmp_path: Path, monkeypatch, target: str,
):
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    staged = tmp_path / "staged-generation"
    shutil.copytree(_generation(tmp_path), staged)
    if target == "receipt_ledger":
        path = staged / "latest_receipt.json"
        value = json.loads(path.read_text())
        value["ledger_sha256"] = "sha256:" + "0" * 64
        path.write_text(canonical_json(value) + "\n")
    elif target == "projection_count":
        path = staged / "all_candidates.json"
        value = json.loads(path.read_text())
        value["generated_from"]["event_count"] += 1
        path.write_text(canonical_json(value) + "\n")
    elif target == "source_balance":
        path = staged / "latest_receipt.json"
        value = json.loads(path.read_text())
        value["source_counts"]["turn_watch"]["mapped"] += 1
        path.write_text(canonical_json(value) + "\n")
    else:
        if target == "parquet":
            path = staged / "current.parquet"
            pd.DataFrame([]).to_parquet(path, index=False)
        else:
            (staged / "unexpected.txt").write_text("not part of the generation contract")
    with pytest.raises(EpisodeContractError):
        writer._validate_generation_payload(staged)


def test_monthly_ledgers_are_canonical_sorted_jsonl_and_suppressions_are_truth(tmp_path: Path, monkeypatch):
    """Unsorted or non-addressed rows would make replay bytes depend on source iteration."""
    _seed_sources(tmp_path)
    document = json.loads(_turn_path(tmp_path).read_text())
    unknown = json.loads(canonical_json(document["rows"][0]))
    unknown["ticker"] = "UNKNOWN"
    document["rows"].append(unknown)
    _turn_path(tmp_path).write_text(canonical_json(_rehash_turn_watch(document)) + "\n")
    receipt = _run_nightly(tmp_path, monkeypatch)

    event_lines = (_generation(tmp_path) / "events" / "2026-11.jsonl").read_text().splitlines()
    suppression_lines = (
        _generation(tmp_path) / "suppressions" / "2026-11.jsonl"
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
    projected = load_candidate_episode_store(_episode_root(tmp_path))
    assert receipt["counts"]["input"] == count
    assert receipt["counts"]["mapped"] == count
    assert receipt["counts"]["suppressed"] == 0
    assert len(projected) == count


def test_downstream_fixture_consumes_only_the_canonical_reader(tmp_path: Path, monkeypatch):
    """A real fixture adapter must resolve the validated HEAD-backed canonical reader."""
    _seed_sources(tmp_path)
    _run_nightly(tmp_path, monkeypatch)
    adapter_path = FIXTURE_ROOT.parent / "downstream_consumer.py"
    spec = importlib.util.spec_from_file_location("candidate_episode_downstream_fixture", adapter_path)
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    assert adapter.load_candidate_episode_store is load_candidate_episode_store
    assert adapter.project_episode_reference(_episode_root(tmp_path)) == [{
        "episode_id": _event_rows(tmp_path)[0]["episode_id"],
        "security_id": "SEC:US-XNAS-ALFA",
        "episode_state": "ACTIVE",
    }]
