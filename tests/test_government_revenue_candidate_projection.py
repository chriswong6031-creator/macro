from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from engine.government_revenue.candidates import (
    build_candidate_observations,
    candidate_queue_content_id,
)
from scripts import build_government_revenue_candidates as projection
from tests.test_government_revenue_candidates import _award_event, _graph, _payload


ROOT = Path(__file__).resolve().parents[1]
FROZEN_AT = "2026-08-03T07:00:00+00:00"


def _fixture_root(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    for name in ("latest.json", "workspace.json", "recipient_entity_graph.json"):
        shutil.copy2(ROOT / "data" / "government_revenue" / name, data_dir / name)
    return tmp_path


def _artifact_bytes(root: Path) -> dict[str, bytes | None]:
    paths = {
        "ledger": root / "data/government_revenue/candidate_ledger.jsonl",
        "queue": root / "data/government_revenue/candidate_queue.json",
        "state": root / "data/government_revenue/candidate_projection_state.json",
        "status": root / "data/government_revenue/candidate_projection_status.json",
        "public": root / "site/government-revenue-data/candidates.json",
    }
    return {name: path.read_bytes() if path.exists() else None for name, path in paths.items()}


def _candidate_projection_with_one_candidate(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    *,
    known_at: str | None = None,
) -> None:
    (root / "data/government_revenue/recipient_entity_graph.json").write_text(
        projection._canonical_json(_graph()),
        encoding="utf-8",
    )
    original_queue = projection.build_candidate_queue
    event = _award_event()
    if known_at is not None:
        event["change"]["known_at"] = known_at
        event["evidence"]["receipts"][0]["known_at"] = known_at
        event["evidence"]["receipts"][0]["retrieved_at"] = known_at

    def candidate_for(generated_at: str) -> dict:
        return build_candidate_observations(
            _payload(event), _graph(), generated_at=generated_at
        )[0]

    def observations(*_args, **kwargs):
        return [deepcopy(candidate_for(kwargs["generated_at"]))]

    def queue(latest, graph, *, generated_at):
        candidate = candidate_for(generated_at)
        result = original_queue(latest, graph, generated_at=generated_at)
        result["candidates"] = [deepcopy(candidate)]
        result["counts"] = dict(result["counts"])
        result["counts"]["total"] = 1
        result["counts"]["exact_linked"] = 1
        result["counts"]["by_family"] = {candidate["candidate_family"]: 1}
        result["counts"]["by_state"] = {candidate["candidate_state"]: 1}
        result["counts"]["by_freshness"] = {"ok": 1}
        result["counts"]["by_exact_link_status"] = {
            "exact_linked": 1,
            "mapping_needed": len(result["mapping_backlog"]),
        }
        # The builder has already supplied the governed shape.  This test only
        # introduces a valid exact candidate to exercise the writer's append
        # gate against the otherwise intentionally empty current fixture.
        result["content_id"] = candidate_queue_content_id(result)
        return result

    monkeypatch.setattr(projection, "build_candidate_observations", observations)
    monkeypatch.setattr(projection, "build_candidate_queue", queue)


def test_current_fixture_projects_honest_empty_queue_and_byte_identical_twins(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    result = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)

    queue_path = root / "data/government_revenue/candidate_queue.json"
    public_path = root / "site/government-revenue-data/candidates.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    status = json.loads(
        (root / "data/government_revenue/candidate_projection_status.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "ok"
    assert result["candidate_count"] == 0
    assert result["mapping_backlog_count"] == 21
    assert queue["counts"]["total"] == 0
    assert queue["counts"]["mapping_needed"] == 21
    assert queue_path.read_bytes() == public_path.read_bytes()
    assert (root / "data/government_revenue/candidate_ledger.jsonl").read_bytes() == b""
    assert status["status"] == "ok"
    assert status["candidate_count"] == 0
    assert status["source_health"]["status"] == "degraded"


def test_same_frozen_run_is_idempotent_and_one_sided_twin_is_remediated(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    first = _artifact_bytes(root)

    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert _artifact_bytes(root) == first

    public_path = root / "site/government-revenue-data/candidates.json"
    public_path.unlink()
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert public_path.read_bytes() == (root / "data/government_revenue/candidate_queue.json").read_bytes()


def test_verifier_allows_generated_at_only_workspace_reassembly(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)

    latest_path = root / "data/government_revenue/latest.json"
    workspace_path = root / "data/government_revenue/workspace.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    reassembled_at = "2026-08-03T08:00:00+00:00"
    latest["generated_at"] = reassembled_at
    workspace["generated_at"] = reassembled_at
    latest["procurement_workspace"] = deepcopy(workspace)
    latest_path.write_text(json.dumps(latest, separators=(",", ":")), encoding="utf-8")
    workspace_path.write_text(projection._canonical_json(workspace), encoding="utf-8")

    verified = projection.verify_candidate_artifacts(root, mirror_public=False)
    assert verified["status"] == "ok"
    assert _artifact_bytes(root) == before


def test_verifier_fails_when_top_level_company_coverage_advances(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)

    latest_path = root / "data/government_revenue/latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["companies"] = latest["companies"][:-1]
    latest_path.write_text(projection._canonical_json(latest), encoding="utf-8")

    with pytest.raises(projection.CandidateProjectionError, match="source binding"):
        projection.verify_candidate_artifacts(root, mirror_public=False)
    assert _artifact_bytes(root) == before


def test_unseen_observation_appends_once_and_prior_prefix_is_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _candidate_projection_with_one_candidate(monkeypatch, root)

    first = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    first_ledger = ledger_path.read_bytes()
    state = json.loads((root / "data/government_revenue/candidate_projection_state.json").read_text())
    assert first["append_count"] == 1
    assert first_ledger.endswith(b"\n")
    assert state["ledger"]["append_count"] == 1
    assert state["ledger"]["prior_line_count"] == 0

    second = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert second["append_count"] == 0
    assert ledger_path.read_bytes() == first_ledger


def test_repeated_observation_keeps_immutable_row_when_envelope_clock_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _candidate_projection_with_one_candidate(monkeypatch, root)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    first_ledger = ledger_path.read_bytes()

    later = "2026-08-03T08:00:00+00:00"
    result = projection.project_candidate_artifacts(root, generated_at=later)

    queue = json.loads((root / "data/government_revenue/candidate_queue.json").read_text())
    state = json.loads((root / "data/government_revenue/candidate_projection_state.json").read_text())
    status = json.loads((root / "data/government_revenue/candidate_projection_status.json").read_text())
    ledger_row = json.loads(ledger_path.read_text().strip())
    assert result["append_count"] == 0
    assert ledger_path.read_bytes() == first_ledger
    assert queue["generated_at"] == later
    assert queue["candidates"] == [ledger_row]
    assert queue["candidates"][0]["generated_at"] == FROZEN_AT
    assert state["generated_at"] == later
    assert status["generated_at"] == later
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


def test_unseen_historical_observation_cannot_backfill_after_prior_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)
    _candidate_projection_with_one_candidate(monkeypatch, root)

    with pytest.raises(
        projection.CandidateProjectionError,
        match="not forward of the prior frozen generated_at clock",
    ):
        projection.project_candidate_artifacts(
            root,
            generated_at="2026-08-03T08:00:00+00:00",
        )

    assert _artifact_bytes(root) == before


def test_unseen_observation_newer_than_prior_materialization_can_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at="2026-08-03T07:30:00+00:00",
    )

    result = projection.project_candidate_artifacts(
        root,
        generated_at="2026-08-03T08:00:00+00:00",
    )

    assert result["append_count"] == 1
    ledger = projection.load_candidate_ledger(
        root / "data/government_revenue/candidate_ledger.jsonl"
    )
    assert ledger.line_count == 1
    assert ledger.observations[0]["known_at"] == "2026-08-03T07:30:00+00:00"


def test_candidate_projection_writer_clock_cannot_regress(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)

    with pytest.raises(
        projection.CandidateProjectionError,
        match="generated_at cannot move backward",
    ):
        projection.project_candidate_artifacts(
            root,
            generated_at="2026-08-03T06:59:59+00:00",
        )

    assert _artifact_bytes(root) == before


def test_verifier_accepts_canonical_generation_and_can_remirror_public_twin(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    assert projection.verify_candidate_artifacts(root) == {"status": "absent"}
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"

    public_path = root / "site/government-revenue-data/candidates.json"
    public_path.unlink()
    with pytest.raises(projection.CandidateProjectionError, match="public twin"):
        projection.verify_candidate_artifacts(root)
    result = projection.verify_candidate_artifacts(root, mirror_public=True)
    assert result["status"] == "ok"
    assert public_path.read_bytes() == (root / "data/government_revenue/candidate_queue.json").read_bytes()


@pytest.mark.parametrize("tamper", ["mutation", "truncation"])
def test_existing_ledger_mutation_or_truncation_fails_before_other_outputs_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    root = _fixture_root(tmp_path)
    _candidate_projection_with_one_candidate(monkeypatch, root)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    if tamper == "mutation":
        ledger_path.write_bytes(ledger_path.read_bytes().replace(b'"NOC"', b'"BAD"', 1))
    else:
        ledger_path.write_bytes(b"")
    before = _artifact_bytes(root)

    with pytest.raises(projection.CandidateProjectionError, match="ledger"):
        projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)

    assert _artifact_bytes(root) == before


def test_corrupt_source_or_authority_fails_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    (root / "data/government_revenue/latest.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(projection.CandidateProjectionError, match="canonical latest"):
        projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert all(value is None for value in _artifact_bytes(root).values())

    root = _fixture_root(tmp_path / "authority")
    original_queue = projection.build_candidate_queue

    def bad_authority(latest, graph, *, generated_at):
        queue = original_queue(latest, graph, generated_at=generated_at)
        queue["authority"] = {**queue["authority"], "can_gate": True}
        return queue

    monkeypatch.setattr(projection, "build_candidate_queue", bad_authority)
    with pytest.raises(projection.CandidateProjectionError, match="queue"):
        projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert all(value is None for value in _artifact_bytes(root).values())

    root = _fixture_root(tmp_path / "queue")

    def bad_queue(latest, graph, *, generated_at):
        queue = original_queue(latest, graph, generated_at=generated_at)
        queue["content_id"] = "grcq1-" + "0" * 24
        return queue

    monkeypatch.setattr(projection, "build_candidate_queue", bad_queue)
    with pytest.raises(projection.CandidateProjectionError, match="queue"):
        projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert all(value is None for value in _artifact_bytes(root).values())


def test_frozen_clock_is_persisted_and_rejects_future_known_source(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    state = json.loads((root / "data/government_revenue/candidate_projection_state.json").read_text())
    status = json.loads((root / "data/government_revenue/candidate_projection_status.json").read_text())
    assert state["generated_at"] == FROZEN_AT
    assert status["generated_at"] == FROZEN_AT

    root = _fixture_root(tmp_path / "future")
    latest_path = root / "data/government_revenue/latest.json"
    workspace_path = root / "data/government_revenue/workspace.json"
    latest = json.loads(latest_path.read_text())
    workspace = json.loads(workspace_path.read_text())
    future = "2026-08-04T00:00:00+00:00"
    latest["known_at"] = future
    latest["procurement_workspace"]["known_at"] = future
    workspace["known_at"] = future
    workspace["bundle_id"] = projection.build_government_revenue._workspace_bundle_id(workspace)
    latest["procurement_workspace"]["bundle_id"] = workspace["bundle_id"]
    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    workspace_path.write_text(json.dumps(workspace), encoding="utf-8")
    with pytest.raises(projection.CandidateProjectionError, match="frozen generated_at"):
        projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert all(value is None for value in _artifact_bytes(root).values())
