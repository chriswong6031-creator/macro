from __future__ import annotations

import json
import shutil
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from engine.government_revenue.candidates import (
    build_candidate_observations,
    candidate_historical_suppression_entry,
    candidate_queue_content_id,
    historical_suppression_entry_key,
    load_candidate_issuance_correction_manifest,
    validate_candidate_historical_suppression_binding,
    validate_candidate_issuance_correction_binding,
)
from engine.government_revenue.entity_resolution import load_recipient_entity_graph
from scripts import build_government_revenue_candidates as projection
from tests.government_revenue_candidate_fixture import (
    ROOT,
    canonical_fixture_root,
    canonical_frozen_at,
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
# Frozen recovery clocks for the exact 5fc incident reconstructed below.
CORRECTION_ACTIVATED_AT = "2026-08-10T04:35:00+00:00"
CORRECTION_REPEAT_AT = "2026-08-10T04:36:00+00:00"
FORWARD_DURING_ACTIVATION_AT = "2026-08-10T04:32:00+00:00"


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


def _incident_correction_root(tmp_path: Path) -> Path:
    """Rebuild the exact 5fc incident predecessor without reading Git history."""
    root = canonical_fixture_root(tmp_path)
    copied = (
        "config/government_revenue/candidate_historical_suppressions.v1.json",
        "config/government_revenue/candidate_issuance_corrections.v1.json",
        "contracts/government_revenue/government_revenue_candidate.v1.schema.json",
        "contracts/government_revenue/government_revenue_candidate_queue.v1.schema.json",
        "contracts/government_revenue/government_revenue_candidate_historical_suppressions.v1.schema.json",
        "contracts/government_revenue/government_revenue_candidate_issuance_corrections.v1.schema.json",
        "data/government_revenue/candidate_ledger.jsonl",
    )
    for relative in copied:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    manifest, _manifest_sha = load_candidate_issuance_correction_manifest(root)
    incident = manifest["incident"]
    inputs = projection.validate_candidate_projection_inputs(
        root,
        generated_at=incident["issued_projection_generated_at"],
    )
    _observations, queue, _queue_id, source_health = projection._current_projection(inputs)
    ledger = projection.load_candidate_ledger(
        root / "data/government_revenue/candidate_ledger.jsonl"
    )
    queue, queue_id = projection._queue_bound_to_immutable_ledger(queue, ledger)
    state = projection._ledger_state(
        inputs=inputs,
        queue=queue,
        queue_content_id=queue_id,
        prior=ledger,
        ledger=ledger,
        append_count=0,
    )
    status = projection._projection_status(
        inputs=inputs,
        queue=queue,
        queue_content_id=queue_id,
        ledger=ledger,
        source_health=source_health,
    )
    artifact_dir = root / "data/government_revenue"
    public_dir = root / "site/government-revenue-data"
    public_dir.mkdir(parents=True, exist_ok=True)
    queue_raw = projection._canonical_bytes(queue)
    state_raw = projection._canonical_bytes(state)
    (artifact_dir / "candidate_queue.json").write_bytes(queue_raw)
    (artifact_dir / "candidate_projection_state.json").write_bytes(state_raw)
    (artifact_dir / "candidate_projection_status.json").write_bytes(
        projection._canonical_bytes(status)
    )
    (public_dir / "candidates.json").write_bytes(queue_raw)
    assert queue_id == incident["issued_queue_content_id"]
    assert sha256(queue_raw).hexdigest() == incident["issued_queue_sha256"]
    assert sha256(state_raw).hexdigest() == incident[
        "issued_projection_state_sha256"
    ]
    return root


def _patch_incident_current_rows(
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    """Apply one deterministic hostile edit to both pure candidate surfaces."""
    original_observations = projection.build_candidate_observations
    original_queue = projection.build_candidate_queue

    def current_rows(latest, graph, *, generated_at):
        rows = original_observations(latest, graph, generated_at=generated_at)
        return mutate(deepcopy(rows), generated_at)

    def observations(latest, graph, *, generated_at):
        return current_rows(latest, graph, generated_at=generated_at)

    def queue(latest, graph, *, generated_at):
        result = original_queue(latest, graph, generated_at=generated_at)
        rows = current_rows(latest, graph, generated_at=generated_at)
        result["candidates"] = deepcopy(rows)
        result["counts"] = {
            **result["counts"],
            "total": len(rows),
            "exact_linked": len(rows),
            "by_family": dict(
                sorted(Counter(row["candidate_family"] for row in rows).items())
            ),
            "by_state": dict(
                sorted(Counter(row["candidate_state"] for row in rows).items())
            ),
            "by_freshness": dict(
                sorted(Counter(row["freshness"]["status"] for row in rows).items())
            ),
            "by_exact_link_status": {
                "exact_linked": len(rows),
                "mapping_needed": len(result["mapping_backlog"]),
            },
        }
        result["content_id"] = candidate_queue_content_id(result)
        return result

    monkeypatch.setattr(projection, "build_candidate_observations", observations)
    monkeypatch.setattr(projection, "build_candidate_queue", queue)


def _rotate_candidate_source(
    row: dict,
    *,
    content_sha256: str,
    known_at: str | None = None,
) -> dict:
    """Restate one valid row under a different official-source content digest."""
    prior_sha256 = row["source_event"]["source_content_id"]
    row["source_event"]["source_content_id"] = content_sha256
    for receipt in row["source_receipt_refs"]:
        if receipt["content_sha256"] == prior_sha256:
            receipt["content_sha256"] = content_sha256
            receipt["ref_id"] = (
                receipt["ref_id"].rsplit(":", 1)[0] + ":" + content_sha256[:16]
            )
            if known_at is not None:
                receipt["known_at"] = known_at
    row["artifact_content_ids"] = sorted(
        content_sha256 if value == prior_sha256 else value
        for value in row["artifact_content_ids"]
    )
    if known_at is not None:
        row["known_at"] = known_at
        row["source_event"]["known_at"] = known_at
        row["freshness"]["event_known_at"] = known_at
    return row


def _install_historical_suppression_manifest(
    root: Path,
    rows: list[dict],
    *,
    reviewed_at: str = NEXT_RUN_AT,
    extra_entries: list[dict] | None = None,
) -> dict:
    """Install one production-shaped reviewed manifest against the prior queue."""
    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )
    state = json.loads(
        (root / "data/government_revenue/candidate_projection_state.json").read_text(
            encoding="utf-8"
        )
    )
    entries = [candidate_historical_suppression_entry(row) for row in rows]
    entries.extend(deepcopy(extra_entries or []))
    entries.sort(key=historical_suppression_entry_key)
    manifest = {
        "contract": "government_revenue.candidate_historical_suppressions.v1",
        "schema_version": "1.0.0",
        "reviewed_at": reviewed_at,
        "predecessor": {
            "queue_content_id": queue["content_id"],
            "projection_generated_at": state["generated_at"],
        },
        "policy": "exact_source_identity_only",
        "entries": entries,
        "authority": {
            "tier": "infrastructure",
            "context_only": True,
            "can_rank": False,
            "can_size": False,
            "can_gate": False,
            "can_originate_signal": False,
            "can_add_candidates": False,
            "can_escalate": False,
        },
        "limitations": [
            "Exact reviewed source identities only; no wildcard suppression.",
            "The decision withholds historical issuance and never retimes an observation.",
            "This manifest has no rank, sizing, gate, signal, candidate, or escalation authority.",
        ],
    }
    schema_rel = Path(
        "contracts/government_revenue/"
        "government_revenue_candidate_historical_suppressions.v1.schema.json"
    )
    (root / schema_rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / schema_rel, root / schema_rel)
    manifest_path = (
        root
        / "config/government_revenue/candidate_historical_suppressions.v1.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        projection._canonical_json(manifest) + "\n",
        encoding="utf-8",
    )
    return manifest


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


def test_current_fixture_projects_honest_source_queue_and_byte_identical_twins(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    result = projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)

    queue_path = root / "data/government_revenue/candidate_queue.json"
    public_path = root / "site/government-revenue-data/candidates.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    status = json.loads(
        (root / "data/government_revenue/candidate_projection_status.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "ok"
    assert result["candidate_count"] == 8
    assert result["mapping_backlog_count"] == 21
    assert queue["counts"]["total"] == 8
    assert queue["counts"]["exact_linked"] == 8
    assert queue["counts"]["mapping_needed"] == 21
    assert queue_path.read_bytes() == public_path.read_bytes()
    assert len(
        (root / "data/government_revenue/candidate_ledger.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ) == 8
    assert status["status"] == "ok"
    assert status["candidate_count"] == 8
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


def test_same_frozen_run_is_idempotent_and_one_sided_twin_is_remediated(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    first = _artifact_bytes(root)
    first_state = json.loads(first["state"])
    assert first_state["ledger"]["append_count"] == 8
    assert first_state["ledger"]["prior_line_count"] == 0

    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    settled = _artifact_bytes(root)
    settled_state = json.loads(settled["state"])
    assert settled["ledger"] == first["ledger"]
    assert settled["queue"] == first["queue"]
    assert settled["public"] == first["public"]
    assert settled["status"] == first["status"]
    assert settled_state["ledger"]["append_count"] == 0
    assert settled_state["ledger"]["prior_line_count"] == 8

    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert _artifact_bytes(root) == settled

    public_path = root / "site/government-revenue-data/candidates.json"
    public_path.unlink()
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    assert public_path.read_bytes() == (root / "data/government_revenue/candidate_queue.json").read_bytes()


def test_exact_incident_is_quarantined_without_rewriting_history_and_activation_is_durable(
    tmp_path: Path,
) -> None:
    root = _incident_correction_root(tmp_path)
    queue_path = root / "data/government_revenue/candidate_queue.json"
    state_path = root / "data/government_revenue/candidate_projection_state.json"
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    incident_queue_raw = queue_path.read_bytes()
    incident_state_raw = state_path.read_bytes()
    incident_queue = json.loads(incident_queue_raw)
    incident_state = json.loads(incident_state_raw)
    incident_ledger = projection.load_candidate_ledger(ledger_path)
    incident_ledger_raw = ledger_path.read_bytes()

    uncorrected = validate_candidate_issuance_correction_binding(
        incident_queue,
        incident_state,
        root=root,
        issued_observations=incident_ledger.observations,
        allow_exact_incident_predecessor=True,
        queue_raw_sha256=sha256(incident_queue_raw).hexdigest(),
        projection_state_raw_sha256=sha256(incident_state_raw).hexdigest(),
        require_correction=True,
    )
    assert uncorrected["status"] == "uncorrected_incident"
    assert uncorrected["issued_count"] == 8
    with pytest.raises(ValueError, match="uncorrected candidate issuance incident"):
        validate_candidate_issuance_correction_binding(
            incident_queue,
            incident_state,
            root=root,
            issued_observations=incident_ledger.observations,
        )
    # The older non-issuance validator remains strict: the correction is a
    # separate audit contract, not permission to reinterpret issued rows as
    # having been withheld.
    with pytest.raises(ValueError, match="was issued as a candidate"):
        validate_candidate_historical_suppression_binding(
            incident_queue,
            incident_state,
            root=root,
            current_observations=incident_queue["candidates"],
            issued_observations=incident_ledger.observations,
            require_manifest=True,
        )

    first = projection.project_candidate_artifacts(
        root,
        generated_at=CORRECTION_ACTIVATED_AT,
    )
    first_queue = json.loads(queue_path.read_text(encoding="utf-8"))
    first_state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = first_queue["coverage"][
        "historical_candidate_issuance_correction"
    ]
    activation = deepcopy(receipt["activation"])
    assert first["candidate_count"] == 0
    assert first["append_count"] == 0
    assert first["suppressed_historical_count"] == 0
    assert first["quarantined_issuance_count"] == 8
    assert first_queue["candidates"] == []
    assert first_queue["recently_matured"] == []
    assert first_queue["counts"]["total"] == 0
    assert (
        first_queue["freshness"]["exact_candidate_availability"]
        == "quarantined_historical_issuance"
    )
    assert "historical_candidate_suppression" not in first_queue["coverage"]
    assert receipt["matched_issued_count"] == 8
    assert receipt["quarantined_count"] == 8
    assert activation["activated_at"] == CORRECTION_ACTIVATED_AT
    assert activation["matched_issued_count"] == 8
    assert ledger_path.read_bytes() == incident_ledger_raw
    assert first_state["ledger"] == {
        "append_count": 0,
        "byte_count": 50790,
        "line_count": 8,
        "prior_byte_count": 50790,
        "prior_line_count": 8,
        "prior_sha256": "920d840a328b6be88600230f93c8353af30520172c682b25b7302fd4124f7820",
        "sha256": "920d840a328b6be88600230f93c8353af30520172c682b25b7302fd4124f7820",
    }
    assert projection.verify_candidate_artifacts(
        root,
        require_historical_suppression_manifest=True,
    )["status"] == "ok"

    repeated = projection.project_candidate_artifacts(
        root,
        generated_at=CORRECTION_REPEAT_AT,
    )
    repeated_queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert repeated["candidate_count"] == 0
    assert repeated["append_count"] == 0
    assert repeated["quarantined_issuance_count"] == 8
    assert ledger_path.read_bytes() == incident_ledger_raw
    assert (
        repeated_queue["coverage"]["historical_candidate_issuance_correction"][
            "activation"
        ]
        == activation
    )
    assert projection.verify_candidate_artifacts(
        root,
        require_historical_suppression_manifest=True,
    )["status"] == "ok"


def test_correction_rejects_mutated_or_truncated_incident_prefix_without_writes(
    tmp_path: Path,
) -> None:
    root = _incident_correction_root(tmp_path)
    queue_path = root / "data/government_revenue/candidate_queue.json"
    state_path = root / "data/government_revenue/candidate_projection_state.json"
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    queue_raw = queue_path.read_bytes()
    state_raw = state_path.read_bytes()
    queue = json.loads(queue_raw)
    state = json.loads(state_raw)
    rows = list(projection.load_candidate_ledger(ledger_path).observations)
    before = _artifact_bytes(root)
    mutated = deepcopy(rows)
    mutated[0]["ticker"] = "BAD"

    for hostile_prefix, message in (
        (mutated, "differs from the incident"),
        (rows[:-1], "prefix is incomplete"),
    ):
        with pytest.raises(ValueError, match=message):
            validate_candidate_issuance_correction_binding(
                queue,
                state,
                root=root,
                issued_observations=hostile_prefix,
                allow_exact_incident_predecessor=True,
                queue_raw_sha256=sha256(queue_raw).hexdigest(),
                projection_state_raw_sha256=sha256(state_raw).hexdigest(),
                require_correction=True,
            )
        assert _artifact_bytes(root) == before


def test_exact_incident_raw_binding_tamper_fails_before_publication(
    tmp_path: Path,
) -> None:
    root = _incident_correction_root(tmp_path)
    queue_path = root / "data/government_revenue/candidate_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    # Keep the queue semantically valid and content-addressed, but change its
    # raw bytes. The incident contract binds the reviewed publication artifact,
    # not merely an equivalent JSON object.
    queue_path.write_text(
        json.dumps(queue, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        encoding="utf-8",
    )
    before = _artifact_bytes(root)

    with pytest.raises(
        projection.CandidateProjectionError,
        match="prior candidate reviewed-history binding is invalid",
    ) as refusal:
        projection.project_candidate_artifacts(
            root,
            generated_at=CORRECTION_ACTIVATED_AT,
        )

    assert "incident predecessor is not exact" in str(refusal.value.__cause__)
    assert _artifact_bytes(root) == before


def test_correction_first_activation_refuses_a_ninth_ledger_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _incident_correction_root(tmp_path)
    before = _artifact_bytes(root)

    def add_forward_row(rows: list[dict], generated_at: str) -> list[dict]:
        extra = _rotate_candidate_source(
            deepcopy(rows[0]),
            content_sha256="f" * 64,
            known_at=FORWARD_DURING_ACTIVATION_AT,
        )
        extra["observation_id"] = "gro1-" + "f" * 24
        extra["generated_at"] = generated_at
        rows.append(extra)
        return rows

    _patch_incident_current_rows(monkeypatch, add_forward_row)
    with pytest.raises(
        projection.CandidateProjectionError,
        match="candidate reviewed-history binding is invalid",
    ) as refusal:
        projection.project_candidate_artifacts(
            root,
            generated_at=CORRECTION_ACTIVATED_AT,
        )

    assert "activation changed the incident ledger" in str(refusal.value.__cause__)
    assert _artifact_bytes(root) == before


def test_same_clock_source_content_rotation_cannot_rebind_quarantined_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _incident_correction_root(tmp_path)
    projection.project_candidate_artifacts(
        root,
        generated_at=CORRECTION_ACTIVATED_AT,
    )
    before = _artifact_bytes(root)

    def rotate_same_clock(rows: list[dict], _generated_at: str) -> list[dict]:
        rows[0] = _rotate_candidate_source(
            rows[0],
            content_sha256="f" * 64,
        )
        return rows

    _patch_incident_current_rows(monkeypatch, rotate_same_clock)
    with pytest.raises(
        projection.CandidateProjectionError,
        match="source identity differs from the immutable ledger row",
    ):
        projection.project_candidate_artifacts(
            root,
            generated_at=CORRECTION_REPEAT_AT,
        )

    assert _artifact_bytes(root) == before


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


def test_reviewed_historical_source_is_withheld_without_ledger_backfill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    ledger_path = root / "data/government_revenue/candidate_ledger.jsonl"
    before_ledger = ledger_path.read_bytes()
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    current_rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    _install_historical_suppression_manifest(root, current_rows)

    result = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )
    receipt = queue["coverage"]["historical_candidate_suppression"]
    assert result["append_count"] == 0
    assert result["suppressed_historical_count"] == 1
    assert ledger_path.read_bytes() == before_ledger
    assert projection.load_candidate_ledger(ledger_path).line_count == 8
    assert queue["candidates"] == []
    assert queue["counts"]["total"] == 0
    assert queue["freshness"]["exact_candidate_availability"] == "withheld_historical"
    assert receipt["matched_count"] == receipt["manifest_entry_count"] == 1
    assert receipt["inactive_count"] == 0
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


def test_historical_suppression_review_cannot_postdate_the_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    _install_historical_suppression_manifest(
        root,
        rows,
        reviewed_at=shifted(NEXT_RUN_AT, minutes=1),
    )

    with pytest.raises(
        projection.CandidateProjectionError,
        match="historical suppression activation proof is invalid",
    ):
        projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert _artifact_bytes(root) == before


def test_suppression_binding_rejects_extra_lineage_and_an_issued_exact_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    _install_historical_suppression_manifest(root, rows)
    projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)
    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )
    state = json.loads(
        (root / "data/government_revenue/candidate_projection_state.json").read_text(
            encoding="utf-8"
        )
    )

    stale_lineage = deepcopy(queue)
    stale_lineage["source_content_ids"].append(
        "candidate-suppression-manifest-sha256:" + "f" * 64
    )
    with pytest.raises(ValueError, match="receipt binding is invalid"):
        validate_candidate_historical_suppression_binding(
            stale_lineage,
            state,
            root=root,
            current_observations=rows,
        )

    with pytest.raises(ValueError, match="source identity was issued"):
        validate_candidate_historical_suppression_binding(
            queue,
            state,
            root=root,
            current_observations=rows,
            issued_observations=rows,
        )


def test_historical_suppression_first_activation_requires_an_exact_bijection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    before = _artifact_bytes(root)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    current_rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    unused = candidate_historical_suppression_entry(current_rows[0])
    unused.update(
        {
            "candidate_id": "grc1-" + "f" * 24,
            "source_event_id": unused["source_event_id"] + "-unused",
            "source_record_id": unused["source_record_id"] + "-unused",
            "source_content_sha256": "f" * 64,
        }
    )
    _install_historical_suppression_manifest(
        root,
        current_rows,
        extra_entries=[unused],
    )

    with pytest.raises(
        projection.CandidateProjectionError,
        match="exact manifest/row bijection",
    ):
        projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert _artifact_bytes(root) == before


def test_inactive_receipt_cannot_forge_a_prior_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    legacy_queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    _install_historical_suppression_manifest(root, rows)
    inputs = projection.validate_candidate_projection_inputs(
        root,
        generated_at=NEXT_RUN_AT,
    )
    current_rows, queue, _queue_id, _source_health = projection._current_projection(
        inputs
    )

    with pytest.raises(
        projection.CandidateProjectionError,
        match="first activation lacks the exact full source bijection",
    ):
        projection._apply_historical_suppression_receipt(
            queue,
            inputs=inputs,
            suppressed=[],
            prior_queue=legacy_queue,
        )

    bound = projection._apply_historical_suppression_receipt(
        queue,
        inputs=inputs,
        suppressed=current_rows,
        prior_queue=legacy_queue,
    )
    forged = deepcopy(bound)
    receipt = forged["coverage"]["historical_candidate_suppression"]
    receipt["matched_count"] = 0
    receipt["inactive_count"] = receipt["manifest_entry_count"]
    receipt["entries"] = []
    forged["content_id"] = candidate_queue_content_id(forged)
    with pytest.raises(
        ValueError,
        match="first activation did not bind the full source bijection",
    ):
        validate_candidate_historical_suppression_binding(
            forged,
            {
                "generated_at": NEXT_RUN_AT,
                "queue_content_id": forged["content_id"],
            },
            root=root,
        )


def test_forward_source_revision_is_not_broadened_into_candidate_wide_suppression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    historical_rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    manifest = _install_historical_suppression_manifest(root, historical_rows)
    projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    monkeypatch.undo()
    forward_at = shifted(NEXT_RUN_AT, minutes=30)
    forward_run_at = shifted(NEXT_RUN_AT, hours=1)
    revised = _award_event()
    revised["change"]["known_at"] = forward_at
    revised["award_change"]["source_identity"]["content_sha256"] = "a" * 64
    revised["evidence"]["receipts"][0]["known_at"] = forward_at
    revised["evidence"]["receipts"][0]["retrieved_at"] = forward_at
    revised["evidence"]["receipts"][0]["content_sha256"] = "a" * 64
    candidates_for = _candidate_projection_over_graph(
        monkeypatch,
        root,
        graph=_graph(),
        events=[revised],
        as_of=utc_date(forward_at),
    )
    forward_row = candidates_for(forward_run_at)[0]
    assert forward_row["candidate_id"] == manifest["entries"][0]["candidate_id"]
    assert (
        forward_row["source_event"]["source_content_id"]
        != manifest["entries"][0]["source_content_sha256"]
    )

    result = projection.project_candidate_artifacts(
        root,
        generated_at=forward_run_at,
    )

    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )
    receipt = queue["coverage"]["historical_candidate_suppression"]
    assert result["append_count"] == 1
    assert result["suppressed_historical_count"] == 0
    assert receipt["matched_count"] == 0
    assert receipt["inactive_count"] == 1
    assert queue["freshness"]["exact_candidate_availability"] == "available"
    assert queue["candidates"][0]["source_event"]["source_content_id"] == "a" * 64
    assert projection.verify_candidate_artifacts(root)["status"] == "ok"


def test_exact_legacy_predecessor_rederives_reviewed_rows_and_rejects_neighbors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    _install_historical_suppression_manifest(root, rows)
    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )
    state = json.loads(
        (root / "data/government_revenue/candidate_projection_state.json").read_text(
            encoding="utf-8"
        )
    )

    legacy = validate_candidate_historical_suppression_binding(
        queue,
        state,
        root=root,
        current_observations=rows,
        require_manifest=True,
    )
    assert legacy["status"] == "legacy_predecessor"
    assert legacy["visible_reviewed_count"] == 1

    neighbor = deepcopy(queue)
    neighbor["content_id"] = "grcq1-" + "0" * 24
    with pytest.raises(ValueError, match="omits the current suppression receipt"):
        validate_candidate_historical_suppression_binding(
            neighbor,
            state,
            root=root,
            current_observations=rows,
        )
    neighbor_state = {**state, "generated_at": NEXT_RUN_AT}
    with pytest.raises(ValueError, match="omits the current suppression receipt"):
        validate_candidate_historical_suppression_binding(
            queue,
            neighbor_state,
            root=root,
            current_observations=rows,
        )

    unknown = deepcopy(rows[0])
    unknown["source_event"]["source_content_id"] = "a" * 64
    with pytest.raises(ValueError, match="no reviewed historical suppression"):
        validate_candidate_historical_suppression_binding(
            queue,
            state,
            root=root,
            current_observations=[unknown],
        )
    duplicate = deepcopy(rows[0])
    duplicate["observation_id"] = "gro1-" + "f" * 24
    with pytest.raises(ValueError, match="duplicate a stable identity"):
        validate_candidate_historical_suppression_binding(
            queue,
            state,
            root=root,
            current_observations=[rows[0], duplicate],
        )


def test_activated_manifest_can_go_inactive_but_a_changed_digest_cannot_rebind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    projection.project_candidate_artifacts(root, generated_at=FROZEN_AT)
    _candidate_projection_with_one_candidate(
        monkeypatch,
        root,
        known_at=BEFORE_FROZEN_AT,
    )
    rows = projection.build_candidate_observations(
        None,
        None,
        generated_at=NEXT_RUN_AT,
    )
    _install_historical_suppression_manifest(root, rows)
    projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    monkeypatch.undo()
    inactive_run_at = shifted(NEXT_RUN_AT, hours=1)
    inactive = projection.project_candidate_artifacts(
        root,
        generated_at=inactive_run_at,
    )
    queue = json.loads(
        (root / "data/government_revenue/candidate_queue.json").read_text(
            encoding="utf-8"
        )
    )
    receipt = queue["coverage"]["historical_candidate_suppression"]
    assert inactive["append_count"] == inactive["suppressed_historical_count"] == 0
    assert receipt["matched_count"] == 0
    assert receipt["inactive_count"] == 1
    assert queue["freshness"]["exact_candidate_availability"] == "not_observed"
    before = _artifact_bytes(root)

    manifest_path = (
        root
        / "config/government_revenue/candidate_historical_suppressions.v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["limitations"].append("A different review must not reuse prior activation.")
    manifest_path.write_text(
        projection._canonical_json(manifest) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        projection.CandidateProjectionError,
        match="prior candidate reviewed-history binding is invalid",
    ):
        projection.project_candidate_artifacts(
            root,
            generated_at=shifted(inactive_run_at, hours=1),
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
        known_at=BETWEEN_RUNS_KNOWN_AT,
    )

    result = projection.project_candidate_artifacts(root, generated_at=NEXT_RUN_AT)

    assert result["append_count"] == 1
    ledger = projection.load_candidate_ledger(
        root / "data/government_revenue/candidate_ledger.jsonl"
    )
    assert ledger.line_count == 9
    assert ledger.observations[-1]["known_at"] == BETWEEN_RUNS_KNOWN_AT


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
