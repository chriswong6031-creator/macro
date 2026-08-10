from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from engine.government_revenue.candidates import (
    build_candidate_observations,
    candidate_queue_content_id,
)
from engine.government_revenue.entity_resolution import load_recipient_entity_graph
from scripts import build_government_revenue_candidates as projection
from tests.government_revenue_candidate_fixture import (
    canonical_frozen_at,
    canonical_fixture_root,
    ROOT,
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

# The first successful post-heal materialization issued this reviewed cohort at
# 2026-08-10T04:15:07Z.  The ledger is append-only: later rows may be added, but
# these exact records may never be deleted, rewritten, or reclassified as
# suppressed history.  The digest covers the complete eight-row semantic JSON,
# independent of future appended rows and line ordering.
_ISSUED_RECOVERY_CANDIDATE_IDS = frozenset(
    {
        "grc1-0d9acfe1eb29619cc9b78e2d",
        "grc1-5c04549c98dc93a935b433d7",
        "grc1-78d7567e22834f8e1a142b43",
        "grc1-8d90edd35a0f32f9120ebdb4",
        "grc1-a5d800c17e0bce45ff9a8aa8",
        "grc1-ab00c51be87b507bfb45e8a2",
        "grc1-cc400940cd4e316d5b80a7b1",
        "grc1-e2e57aacdde17def7eeb01d6",
    }
)
_ISSUED_RECOVERY_COHORT_SHA256 = (
    "a6a93726a9cde15da97e5d883d6f16c7c5ab6efe0ca07eecf0e414f0bef148ab"
)
_DISPLAY_ONLY_AUTHORITY = {
    "tier": "display",
    "context_only": True,
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_add_candidates": False,
    "can_escalate": False,
}


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


#: Distinct reviewed-receipt digests for the synthesized graph rows below.
_EXTRA_SHA = {"noc-b": "c" * 64, "lmt": "d" * 64}
#: Source identity of the synthesized second issuer's award action.
_LMT_ACTION_SHA = "e" * 64


def _extra_evidence(graph: dict, suffix: str, content_sha256: str) -> dict:
    """Clone the fixture's reviewed receipt under a fresh, distinct identity."""
    # Derived from the receipt digest, never from `hash()`: string hashing is
    # salted per interpreter, so a `hash()`-derived row would give this fixture a
    # different graph digest in every process.
    row = deepcopy(graph["evidence"][0])
    row["evidence_id"] = f"evidence:{suffix}"
    row["record_id"] = f"0000000000-26-{int(content_sha256[:6], 16) % 1000000:06d}"
    row["url"] = f"https://www.sec.gov/Archives/edgar/data/1/{suffix}.htm"
    row["content_sha256"] = content_sha256
    row["source_ref"] = f"recipient-evidence:sha256:{content_sha256}"
    return row


def _multi_row_graph() -> dict:
    """The fixture graph with two reviewed receipts.

    Every collection in ``_graph()`` holds exactly one row, and a permutation of
    a one-row list is the identity.  A row-order regression is therefore only
    observable against a graph that has more than one row somewhere.
    """
    graph = _graph()
    graph["evidence"].append(_extra_evidence(graph, "noc-b", _EXTRA_SHA["noc-b"]))
    return graph


def _row_reordered(graph: dict) -> dict:
    """Return the same graph content with every collection's rows reversed."""
    reordered = deepcopy(graph)
    for key in ("evidence", "companies", "legal_entities", "identifiers", "ownership_edges"):
        reordered[key].reverse()
    return reordered


def _graph_with_added_receipt(graph: dict, marker: str) -> dict:
    """Return a legitimately *edited* graph: one more reviewed receipt."""
    grown = deepcopy(graph)
    content_sha256 = sha256(marker.encode("utf-8")).hexdigest()
    grown["evidence"].append(_extra_evidence(grown, marker, content_sha256))
    return grown


def _two_issuer_graph() -> dict:
    """``_multi_row_graph()`` grown by one fully reviewed second issuer.

    This is the production-shaped curation increment: a new reviewed UEI, its
    entity, its ownership edge, its receipt, and a new ``graph_id`` generation.
    """
    graph = _multi_row_graph()
    graph["graph_id"] = "recipient-graph:test-noc-lmt"
    graph["evidence"].append(_extra_evidence(graph, "lmt", _EXTRA_SHA["lmt"]))
    company = deepcopy(graph["companies"][0])
    company.update(
        {"company_id": "issuer:lmt", "ticker": "LMT", "evidence_refs": ["evidence:lmt"]}
    )
    graph["companies"].append(company)
    entity = deepcopy(graph["legal_entities"][0])
    entity.update(
        {
            "entity_id": "entity:lmt",
            "canonical_name": "Lockheed Martin Systems Corporation",
            "evidence_refs": ["evidence:lmt"],
        }
    )
    graph["legal_entities"].append(entity)
    identifier = deepcopy(graph["identifiers"][0])
    identifier.update(
        {
            "identifier_id": "identifier:lmt",
            "entity_id": "entity:lmt",
            "value": "LMTDEFGHJKLM",
            "evidence_refs": ["evidence:lmt"],
        }
    )
    graph["identifiers"].append(identifier)
    edge = deepcopy(graph["ownership_edges"][0])
    edge.update(
        {
            "edge_id": "edge:lmt",
            "child_entity_id": "entity:lmt",
            "parent_company_id": "issuer:lmt",
            "evidence_refs": ["evidence:lmt"],
        }
    )
    graph["ownership_edges"].append(edge)
    return graph


def _lmt_award_event(known_at: str) -> dict:
    """A second receipt-bound award event, mapped to the second issuer."""
    event = _award_event()
    event["event_id"] = "govawd-lmt-001"
    event["record_id"] = "CONT_AWD_TEST_002"
    event["change"]["known_at"] = known_at
    event["award_change"]["source_identity"]["content_sha256"] = _LMT_ACTION_SHA
    event["amounts"][0]["source_ref"] = "receipt:action:2"
    event["listed_company_impacts"] = [
        {
            "ticker": "LMT",
            "company_name": "Lockheed Martin Corporation",
            "issuer_company_id": "issuer:lmt",
            "relation_semantic": "reviewed",
            "resolution_state": "reviewed",
            "ownership_path": [
                {
                    **deepcopy(event["listed_company_impacts"][0]["ownership_path"][0]),
                    "edge_id": "edge:lmt",
                    "child_entity_id": "entity:lmt",
                    "parent_company_id": "issuer:lmt",
                    "evidence_refs": ["evidence:lmt"],
                }
            ],
            "evidence_refs": ["evidence:lmt"],
        }
    ]
    event["evidence"]["receipts"][0].update(
        {
            "ref_id": "receipt:action:2",
            "record_id": "CONT_AWD_TEST_002",
            "known_at": known_at,
            "retrieved_at": known_at,
            "content_sha256": _LMT_ACTION_SHA,
        }
    )
    return event


def _graph_reviewed_at(graph: dict, known_at: str) -> dict:
    """Return the same graph with every reviewed claim learned at ``known_at``.

    A curator re-dating the evidence behind an already-recorded mapping is the
    one edit that can move a *recorded* candidate's clock, in either direction.
    """
    restated = deepcopy(graph)
    restated["graph_known_at"] = known_at
    restated["graph_effective_at"] = known_at
    for key in ("evidence", "companies", "legal_entities", "identifiers", "ownership_edges"):
        for row in restated[key]:
            row["known_at"] = known_at
            if "retrieved_at" in row:
                row["retrieved_at"] = known_at
    return restated


def _graph_digest(graph: dict) -> str:
    return load_recipient_entity_graph(graph, as_of=utc_date(FROZEN_AT))["graph_digest"]


def _candidate_projection_over_graph(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    *,
    graph: dict,
    events: list[dict],
    as_of: str | None = None,
):
    """Install ``graph`` as the root's reviewed graph and project ``events`` on it.

    The current canonical generation carries no exact candidate at all, so the
    writer's append/freeze gates can only be exercised against a synthesized
    pair.  Everything here still runs through the *pure* engine: the injection
    supplies the sources, never a hand-built candidate row, so the identity
    recipe under test is the shipping one.  Returns the builder so a test can
    ask for the very rows the writer will see.
    """
    (root / "data/government_revenue/recipient_entity_graph.json").write_text(
        projection._canonical_json(graph),
        encoding="utf-8",
    )
    payload = _payload()
    payload["procurement_workspace"]["events"] = deepcopy(events)
    if as_of is not None:
        payload["as_of"] = max(payload["as_of"], as_of)
    original_queue = projection.build_candidate_queue

    def candidates_for(generated_at: str) -> list[dict]:
        rows = build_candidate_observations(
            payload, deepcopy(graph), generated_at=generated_at
        )
        rows = sorted(rows, key=lambda row: row["candidate_id"])
        rows.sort(key=lambda row: row["known_at"], reverse=True)
        return rows

    def observations(*_args, **kwargs):
        return deepcopy(candidates_for(kwargs["generated_at"]))

    def queue(latest, recipient_graph, *, generated_at):
        rows = candidates_for(generated_at)
        result = original_queue(latest, recipient_graph, generated_at=generated_at)
        result["candidates"] = deepcopy(rows)
        result["counts"] = {
            **result["counts"],
            "total": len(rows),
            "exact_linked": len(rows),
            "by_family": dict(sorted(Counter(row["candidate_family"] for row in rows).items())),
            "by_state": dict(sorted(Counter(row["candidate_state"] for row in rows).items())),
            "by_freshness": dict(sorted(Counter(row["freshness"]["status"] for row in rows).items())),
            "by_exact_link_status": {
                "exact_linked": len(rows),
                "mapping_needed": len(result["mapping_backlog"]),
            },
        }
        result["content_id"] = candidate_queue_content_id(result)
        return result

    monkeypatch.setattr(projection, "build_candidate_observations", observations)
    monkeypatch.setattr(projection, "build_candidate_queue", queue)
    return candidates_for


def _project_empty_candidate_baseline(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
) -> dict:
    """Materialize an explicit empty synthetic source, then release its patches."""
    _candidate_projection_over_graph(
        monkeypatch,
        root,
        graph=_graph(),
        events=[],
    )
    result = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    monkeypatch.undo()
    return result


def test_current_fixture_projects_issued_queue_and_byte_identical_twins(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    result = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)

    queue_path = root / "data/government_revenue/candidate_queue.json"
    public_path = root / "site/government-revenue-data/candidates.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    status = json.loads(
        (root / "data/government_revenue/candidate_projection_status.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "ok"
    assert result["candidate_count"] >= len(_ISSUED_RECOVERY_CANDIDATE_IDS)
    assert result["mapping_backlog_count"] == 21
    assert queue["counts"]["total"] == result["candidate_count"]
    assert queue["counts"]["mapping_needed"] == 21
    assert queue_path.read_bytes() == public_path.read_bytes()
    ledger = projection.load_candidate_ledger(
        root / "data/government_revenue/candidate_ledger.jsonl"
    )
    assert ledger.line_count == result["candidate_count"]
    assert _ISSUED_RECOVERY_CANDIDATE_IDS <= {
        row["candidate_id"] for row in ledger.observations
    }
    assert status["status"] == "ok"
    assert status["candidate_count"] == result["candidate_count"]
    # Source health is reported from the canonical inputs, never defaulted rosy.
    # A hand-typed literal here is the same scheduled failure this suite's fixture
    # module was written to end: the award-event rail sat at "unavailable" for days
    # and activated on 2026-08-08T18:30Z, flipping the composed status degraded->ok
    # with no code change. So bind the published award-event status to the very
    # document the fixture root copied -- the two move together by construction.
    # The literal snapshot tripwire for this state lives in the live-probe suite
    # (tests/test_government_revenue_candidates::test_current_truth_*), which is
    # where a human is meant to re-read it when the rail moves.
    canonical_award_status = json.loads(
        (root / "data/government_revenue/latest.json").read_text(encoding="utf-8")
    )["procurement_workspace"]["freshness"]["award_events"]["status"]
    assert status["source_health"]["award_events_status"] == canonical_award_status
    assert status["source_health"]["status"] in {"ok", "degraded"}


def test_issued_recovery_cohort_is_immutable_context_and_never_suppressed() -> None:
    """The live first issuance cannot be retroactively rewritten as withheld.

    #5207 healed the schema door and the serialized live writer appended eight
    reviewed rows before the proposed suppression control could land.  Their
    issuance is now immutable history: preserve their complete semantic bytes,
    keep every authority action false, and reject any later suppression
    manifest that overlaps an already-issued source identity.
    """
    ledger_path = ROOT / "data/government_revenue/candidate_ledger.jsonl"
    rows = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cohort = sorted(
        (
            row
            for row in rows
            if row.get("candidate_id") in _ISSUED_RECOVERY_CANDIDATE_IDS
        ),
        key=lambda row: row["candidate_id"],
    )
    assert {row["candidate_id"] for row in cohort} == _ISSUED_RECOVERY_CANDIDATE_IDS
    cohort_sha256 = sha256(
        json.dumps(cohort, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert cohort_sha256 == _ISSUED_RECOVERY_COHORT_SHA256

    for row in cohort:
        assert row["authority"] == _DISPLAY_ONLY_AUTHORITY
        assert row["candidate_scope"] == "government_revenue_research"
        assert row["is_neuralweb_trade_candidate"] is False

    suppression_path = (
        ROOT
        / "config/government_revenue/candidate_historical_suppressions.v1.json"
    )
    assert not suppression_path.exists(), (
        "active historical-suppression plumbing cannot be introduced after the "
        "reviewed cohort has already been issued; design any future control as a "
        "new forward-only contract"
    )


def test_same_frozen_run_keeps_durable_bytes_and_remediates_one_sided_twin(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    first = _artifact_bytes(root)

    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    second = _artifact_bytes(root)
    for artifact in ("ledger", "queue", "status", "public"):
        assert second[artifact] == first[artifact]
    first_state = json.loads(first["state"])
    second_state = json.loads(second["state"])
    assert {
        key: value for key, value in second_state.items() if key != "ledger"
    } == {key: value for key, value in first_state.items() if key != "ledger"}
    assert second_state["ledger"]["append_count"] == 0
    assert second_state["ledger"]["prior_line_count"] == first_state["ledger"]["line_count"]
    assert second_state["ledger"]["prior_sha256"] == first_state["ledger"]["sha256"]
    assert second_state["ledger"]["sha256"] == first_state["ledger"]["sha256"]

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


def test_first_issuance_into_an_empty_ledger_records_historical_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty ledger has no issuance history, so first issuance is not a backfill.

    Every broken-admission generation issued zero candidates while advancing the
    frozen clock, and first-seen evidence clocks never move forward -- refusing
    here wedged the serialized live lane permanently once #5086 repaired the
    event contract (render run 31333981567).  The row keeps its honest evidence
    ``known_at`` beside the issuing run's ``generated_at``.
    """
    root = _fixture_root(tmp_path)
    _project_empty_candidate_baseline(monkeypatch, root)
    _candidate_projection_with_one_candidate(monkeypatch, root)

    result = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert result["append_count"] == 1
    ledger = projection.load_candidate_ledger(
        root / "data/government_revenue/candidate_ledger.jsonl"
    )
    assert ledger.line_count == 1
    row = ledger.observations[0]
    assert row["generated_at"] == NEXT_RUN_AT
    assert projection._instant(
        row["known_at"], label="issued observation known_at"
    ) <= projection._instant(FROZEN_AT, label="frozen clock")
    notice = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if "govrev-candidate-first-issuance" in line
    )
    assert notice.startswith("::notice ")
    assert row["observation_id"] in notice
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


def test_first_issuance_escape_arms_the_gate_once_any_row_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The empty-ledger admission is one-shot: a frozen ledger refuses again."""
    root = _fixture_root(tmp_path)
    _project_empty_candidate_baseline(monkeypatch, root)
    _candidate_projection_over_graph(
        monkeypatch, root, graph=_multi_row_graph(), events=[_award_event()]
    )
    first = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)
    assert first["append_count"] == 1
    before = _artifact_bytes(root)

    _candidate_projection_over_graph(
        monkeypatch,
        root,
        graph=_two_issuer_graph(),
        events=[_award_event(), _lmt_award_event(BEFORE_FROZEN_AT)],
        as_of=utc_date(BEFORE_FROZEN_AT),
    )
    with pytest.raises(
        projection.CandidateProjectionError,
        match="not forward of the prior frozen generated_at clock",
    ):
        projection.project_candidate_artifacts(
            root, generated_at=shifted(NEXT_RUN_AT, hours=1)
        )

    assert _artifact_bytes(root) == before


def test_unseen_observation_newer_than_prior_materialization_can_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _project_empty_candidate_baseline(monkeypatch, root)
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


def test_reviewed_graph_row_reordering_is_not_a_new_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A permutation of the reviewed graph is not a change to the reviewed graph.

    The graph digest is a *content* digest.  When it moved on row order it flowed
    into every candidate's ``observation_id``, so a re-serialized graph made the
    whole ledger re-present as unseen-with-an-old-clock and the writer refused
    to publish -- every night, forever.
    """
    base = _multi_row_graph()
    reordered = _row_reordered(base)
    assert projection._canonical_json(reordered) != projection._canonical_json(base)
    assert _graph_digest(reordered) == _graph_digest(base)

    root = _fixture_root(tmp_path)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    _candidate_projection_over_graph(monkeypatch, root, graph=base, events=[_award_event()])
    first = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    seeded = ledger_path.read_bytes()
    assert first["append_count"] == 1

    _candidate_projection_over_graph(
        monkeypatch, root, graph=reordered, events=[_award_event()]
    )
    second = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert second["append_count"] == 0
    assert ledger_path.read_bytes() == seeded
    assert projection.load_candidate_ledger(ledger_path).line_count == 1
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


def test_reviewed_graph_growth_freezes_issued_candidates_and_appends_only_new_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A curation increment must not re-issue, and must not refuse, what is issued.

    Issuance identity is ``candidate_id`` -- family, issuer, event -- so a new
    reviewed UEI under a new ``graph_id`` leaves every already-issued candidate
    exactly where it is and appends only what the new mapping genuinely made
    visible.
    """
    root = _fixture_root(tmp_path)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    base = _multi_row_graph()
    _candidate_projection_over_graph(monkeypatch, root, graph=base, events=[_award_event()])
    seeded_result = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    seeded = ledger_path.read_bytes()
    issued = json.loads(seeded.decode("utf-8").strip())
    assert seeded_result["append_count"] == 1

    grown = _two_issuer_graph()
    assert _graph_digest(grown) != _graph_digest(base)
    _candidate_projection_over_graph(
        monkeypatch,
        root,
        graph=grown,
        events=[_award_event(), _lmt_award_event(BETWEEN_RUNS_KNOWN_AT)],
        as_of=utc_date(BETWEEN_RUNS_KNOWN_AT),
    )
    result = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    ledger = projection.load_candidate_ledger(ledger_path)
    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(encoding="utf-8")
    )
    by_candidate = {row["candidate_id"]: row for row in queue["candidates"]}
    assert result["append_count"] == 1
    assert ledger.line_count == 2
    # The already-issued row keeps its bytes, including the graph generation it
    # was issued under.  Only the genuinely new candidate is appended.
    assert ledger_path.read_bytes().startswith(seeded)
    assert ledger.observations[0] == issued
    assert sorted(row["ticker"] for row in ledger.observations) == ["LMT", "NOC"]
    assert by_candidate[issued["candidate_id"]] == issued
    new_row = next(row for row in queue["candidates"] if row["ticker"] == "LMT")
    assert new_row["issuer_resolution_ref"]["graph_digest"] == _graph_digest(grown)
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


def test_first_seen_candidate_with_historical_clock_is_refused_beside_a_frozen_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-backfill still bites, and names only the candidate it is refusing."""
    root = _fixture_root(tmp_path)
    base = _multi_row_graph()
    _candidate_projection_over_graph(monkeypatch, root, graph=base, events=[_award_event()])
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)

    # The second issuer's event was knowable before the frozen clock: appending it
    # now would be a backfill, whatever the first candidate's ledger row says.
    candidates_for = _candidate_projection_over_graph(
        monkeypatch,
        root,
        graph=_two_issuer_graph(),
        events=[_award_event(), _lmt_award_event(BEFORE_FROZEN_AT)],
        as_of=utc_date(BEFORE_FROZEN_AT),
    )
    rows = {row["ticker"]: row for row in candidates_for(NEXT_RUN_AT)}

    with pytest.raises(
        projection.CandidateProjectionError,
        match="not forward of the prior frozen generated_at clock",
    ) as refusal:
        projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert rows["LMT"]["observation_id"] in str(refusal.value)
    assert rows["NOC"]["observation_id"] not in str(refusal.value)
    assert _artifact_bytes(root) == before


def test_repeated_reviewed_graph_edits_never_grow_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ledger counts issuances, not graph generations."""
    root = _fixture_root(tmp_path)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    graph = _multi_row_graph()
    _candidate_projection_over_graph(monkeypatch, root, graph=graph, events=[_award_event()])
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    seeded = ledger_path.read_bytes()
    digests = {_graph_digest(graph)}

    for edit in range(1, 4):
        graph = _graph_with_added_receipt(graph, f"edit-{edit}")
        digests.add(_graph_digest(graph))
        _candidate_projection_over_graph(
            monkeypatch, root, graph=graph, events=[_award_event()]
        )
        result = projection.project_candidate_artifacts(
            root, generated_at=shifted(FROZEN_AT, hours=edit + 1)
        )
        assert result["append_count"] == 0
        assert ledger_path.read_bytes() == seeded
        assert projection.load_candidate_ledger(ledger_path).line_count == 1

    # Each edit really did move the graph digest -- otherwise the law above would
    # hold for the trivial reason that nothing changed.
    assert len(digests) == 4
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


def test_recuration_behind_the_frozen_clock_publishes_history_instead_of_refusing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back-dated evidence cannot rewrite a recorded observation, or stop the run.

    Re-dating the reviewed mapping earlier moves a recorded candidate's
    ``known_at`` backwards, so the current re-derivation carries a clock the
    ledger never recorded and -- being behind the frozen writer clock -- can
    never record.  History stays authoritative and publication continues.
    """
    root = _fixture_root(tmp_path)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    late = _graph_reviewed_at(_multi_row_graph(), "2026-08-02T18:00:00+00:00")
    _candidate_projection_over_graph(monkeypatch, root, graph=late, events=[_award_event()])
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    seeded = ledger_path.read_bytes()
    recorded = json.loads(seeded.decode("utf-8").strip())
    assert recorded["known_at"] == "2026-08-02T18:00:00+00:00"

    early = _graph_reviewed_at(_multi_row_graph(), "2026-08-01T00:00:00+00:00")
    candidates_for = _candidate_projection_over_graph(
        monkeypatch, root, graph=early, events=[_award_event()]
    )
    # The re-derivation really does carry an earlier, never-recorded clock.
    assert candidates_for(NEXT_RUN_AT)[0]["known_at"] < recorded["known_at"]

    result = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(encoding="utf-8")
    )
    assert result["append_count"] == 0
    assert ledger_path.read_bytes() == seeded
    assert queue["candidates"] == [recorded]
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


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
