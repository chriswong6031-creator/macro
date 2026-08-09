from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from engine.government_revenue.candidates import (
    build_candidate_observations,
    candidate_queue_content_id,
)
from scripts import build_government_revenue_candidates as projection
from tests.government_revenue_candidate_fixture import (
    canonical_frozen_at,
    canonical_fixture_root,
    shifted,
    utc_date,
)
from tests.test_government_revenue_candidates import _award_event, _graph, _payload


# Derived from the canonical inputs `_fixture_root` copies, never hand-typed --
# see `tests/government_revenue_candidate_fixture` for why a wall-clock literal
# here is a scheduled failure rather than a constant.
FROZEN_AT = canonical_frozen_at()
#: A later run over the same sources: reassembly, clock advance, append window.
NEXT_RUN_AT = shifted(FROZEN_AT, hours=1)
#: An observation known between the two runs above -- appendable, not a backfill.
BETWEEN_RUNS_KNOWN_AT = shifted(FROZEN_AT, minutes=30)
#: One second behind the first run: the writer's clock must refuse to regress.
BEFORE_FROZEN_AT = shifted(FROZEN_AT, seconds=-1)
#: A source known after the run that reads it -- the monotonicity guard's target.
FUTURE_KNOWN_AT = shifted(FROZEN_AT, hours=9)


def _fixture_root(tmp_path: Path) -> Path:
    return canonical_fixture_root(tmp_path)


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
    payload = _payload(event)
    if known_at is not None:
        # `build_candidate_observations` drops any receipt known after the
        # payload's `as_of` end-of-day.  The clocks a caller pins here are
        # offsets from the run clock, which tracks the live canonical vintage,
        # so the hand-authored analysis window has to be widened to cover them
        # -- otherwise the candidate silently vanishes and the append gate under
        # test is never exercised at all.
        payload["as_of"] = max(payload["as_of"], utc_date(known_at))

    def candidate_for(generated_at: str) -> dict:
        return build_candidate_observations(
            payload, _graph(), generated_at=generated_at
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


def test_current_fixture_projects_an_honest_queue_and_byte_identical_twins(tmp_path: Path) -> None:
    """Live probe over the committed fixture, consistency-form.

    The prior snapshot literals ("21", "degraded", ledger == b"") turned every
    legitimate data advance into a scheduled red — the 2026-08-08 award-event
    activation flipped source_health to "ok" with no defect anywhere.  Each
    expectation is now the builder's own registered derivation or a writer
    honesty invariant, so the probe follows legitimate truth while still biting
    on a wrong aggregate, mismatched twins, or a ledger append with nothing to
    append.
    """
    root = _fixture_root(tmp_path)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    ledger_before = ledger_path.read_bytes() if ledger_path.exists() else b""

    result = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)

    queue_path = root / "data/government_revenue/candidate_queue.json"
    public_path = root / "site/government-revenue-data/candidates.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    status = json.loads(
        (root / "data/government_revenue/candidate_projection_status.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "ok"
    assert result["mapping_backlog_count"] == len(queue["mapping_backlog"])
    assert queue["counts"]["mapping_needed"] == len(queue["mapping_backlog"])
    assert queue_path.read_bytes() == public_path.read_bytes()
    assert status["status"] == "ok"
    assert status["candidate_count"] == queue["counts"]["total"]
    assert result["candidate_count"] == queue["counts"]["total"]
    if queue["counts"]["total"] == 0:
        assert ledger_path.read_bytes() == ledger_before
    health = status["source_health"]
    assert health["status"] == (
        "ok"
        if health["award_events_status"] == "ok" and health["recipient_graph_status"] == "ready"
        else "degraded"
    )


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
    reassembled_at = NEXT_RUN_AT
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

    later = NEXT_RUN_AT
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
        projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert _artifact_bytes(root) == before


def test_unseen_observation_newer_than_prior_materialization_can_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BETWEEN_RUNS_KNOWN_AT,
    )

    result = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert result["append_count"] == 1
    ledger = projection.load_candidate_ledger(
        root / "data/government_revenue/candidate_ledger.jsonl"
    )
    assert ledger.line_count == 1
    assert ledger.observations[0]["known_at"] == BETWEEN_RUNS_KNOWN_AT


def test_candidate_projection_writer_clock_cannot_regress(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)

    with pytest.raises(
        projection.CandidateProjectionError,
        match="generated_at cannot move backward",
    ):
        projection.project_candidate_artifacts(root, generated_at=BEFORE_FROZEN_AT)

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
    future = FUTURE_KNOWN_AT
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
