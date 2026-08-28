"""Wave 9F gates — Government Revenue as Prophet post-selection annotation.

Every acceptance gate in the handoff's Wave 9F section is one test here:

  * candidate membership, rank, confidence, size, gates, and execution decision
    are byte-identical with the adapter on/off;
  * timeouts and malformed Government Revenue packets fail open to Prophet's
    preexisting decision;
  * Prophet cannot call Government Revenue to source a candidate — proven over
    the TRANSITIVE import graph, not just direct imports;
  * authority remains display/context, mirroring
    ``data/government_revenue/candidate_queue.json``;
  * every rendered annotation traces to the exact candidate/evidence generation.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest

pytest.importorskip("pandas")

from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

from engine.government_revenue import prophet_annotation as pa  # noqa: E402
from engine.government_revenue import shadow_context as sc  # noqa: E402
from engine.government_revenue.candidates import (  # noqa: E402
    build_candidate_queue,
)
from tests.test_government_revenue_candidates import (  # noqa: E402
    GENERATED_AT,
    _award_event,
    _graph,
    _payload,
)
from tests.test_government_revenue_shadow_context import _present_legs  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts" / "government_revenue"


def _queue() -> dict:
    queue = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    assert queue["candidates"], "the candidates fixture must yield an exact candidate"
    return queue


def _packet_builder(tmp_path: Path):
    def _build(candidate):
        return sc.build_shadow_packet(candidate, repo_root=tmp_path, legs_provider=_present_legs)

    return _build


def _plan(ticker: str, *, priority: float, conviction: int) -> dict:
    """A plan shaped like ``prophet_bridge.originate_plans`` output.

    Only the DECISION projection matters to these gates, but the surrounding
    display fields are present so a mutation of one cannot hide behind a
    too-narrow fixture.
    """
    return {
        "id": f"{ticker}-BULL-2026-08-03",
        "asset": ticker,
        "direction": "BULL",
        "trigger": {"kind": "break_above", "level": 500.0},
        "entry": 500.0,
        "invalidation": 470.0,
        "targets": [{"label": "T1", "level": 545.0}, {"label": "T2", "level": 590.0}],
        "horizon_days": 45,
        "min_hold_days": 10,
        "tranche": {"initial_pct": 50, "add_pct": 50},
        "option_contract": None,
        "stage_tilt": {"stage": 2, "tilt": "with"},
        "thesis": "Momentum with a clean base.",
        "thesis_zh": "动能配合干净的基底。",
        "_priority_score": priority,
        "_conviction_score": conviction,
        "_act_level": 3,
        "_r_unit": 30.0,
        "_gate_go": True,
        "_signal_date": "2026-08-03",
    }


def _plans() -> list[dict]:
    return [
        _plan("NOC", priority=88.5, conviction=82),
        _plan("LMT", priority=71.25, conviction=70),
    ]


def _envelope(tmp_path: Path, *, plans: list[dict] | None = None) -> dict:
    rows = plans if plans is not None else _plans()
    return pa.build_annotation_envelope(
        _queue(),
        selected_tickers=[row["asset"] for row in rows],
        generated_at=GENERATED_AT,
        packet_builder=_packet_builder(tmp_path),
    )


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    from referencing import Registry, Resource

    annotation = _schema("government_revenue_prophet_annotation.v1.schema.json")
    shadow = _schema("government_revenue_shadow_context.v1.schema.json")
    registry = Registry().with_resource(shadow["$id"], Resource.from_contents(shadow))
    registry = registry.with_resource(annotation["$id"], Resource.from_contents(annotation))
    return Draft202012Validator(annotation, registry=registry, format_checker=FormatChecker())


# --------------------------------------------------------------------------- #
# GATE 1 — byte-identical decision with the adapter on/off
# --------------------------------------------------------------------------- #


def _decision_bytes(plans) -> str:
    """Membership, order, and every decision field, as bytes."""
    return json.dumps(
        [{field: plan.get(field) for field in pa.PLAN_DECISION_FIELDS} for plan in plans],
        sort_keys=True,
        separators=(",", ":"),
    )


def test_prophet_decision_is_byte_identical_with_the_adapter_on_and_off(
    tmp_path: Path,
) -> None:
    """The gate, stated as bytes.

    Asserted three ways so a single weak comparison cannot carry it: the decision
    projection's bytes, the module's own fingerprint, and the plan ids in order.
    """
    baseline = _plans()
    baseline_bytes = _decision_bytes(baseline)
    baseline_fingerprint = pa.decision_fingerprint(baseline)

    annotated = pa.annotate_selected_plans(baseline, _envelope(tmp_path))

    assert _decision_bytes(annotated) == baseline_bytes
    assert pa.decision_fingerprint(annotated) == baseline_fingerprint
    assert [plan["id"] for plan in annotated] == [plan["id"] for plan in baseline]
    assert [plan["asset"] for plan in annotated] == [plan["asset"] for plan in baseline]
    # And the annotation actually landed, so the byte-identity is not vacuous.
    assert pa.ANNOTATION_PLAN_KEY in annotated[0]


def test_adapter_cannot_add_remove_or_reorder_a_plan(tmp_path: Path) -> None:
    """Membership and rank are the list itself; both must survive untouched."""
    baseline = _plans()

    annotated = pa.annotate_selected_plans(baseline, _envelope(tmp_path))

    assert len(annotated) == len(baseline)
    assert [plan["_priority_score"] for plan in annotated] == [88.5, 71.25]


def test_adapter_never_mutates_the_plans_it_was_handed(tmp_path: Path) -> None:
    """In-place mutation is the realistic failure; the input list must be pristine."""
    baseline = _plans()
    snapshot = deepcopy(baseline)

    pa.annotate_selected_plans(baseline, _envelope(tmp_path))

    assert baseline == snapshot


def test_a_candidate_for_an_unselected_name_is_never_annotated(tmp_path: Path) -> None:
    """Govrev cannot push a name in: no plan, no annotation, no delivery."""
    plans = [_plan("LMT", priority=71.25, conviction=70)]

    envelope = _envelope(tmp_path, plans=plans)
    annotated = pa.annotate_selected_plans(plans, envelope)

    assert envelope["annotations"] == []
    assert envelope["coverage"]["annotated_candidate_count"] == 0
    assert pa.ANNOTATION_PLAN_KEY not in annotated[0]
    assert _decision_bytes(annotated) == _decision_bytes(plans)


def test_annotation_attaches_only_to_the_matching_selected_plan(tmp_path: Path) -> None:
    annotated = pa.annotate_selected_plans(_plans(), _envelope(tmp_path))

    by_asset = {plan["asset"]: plan for plan in annotated}
    assert pa.ANNOTATION_PLAN_KEY in by_asset["NOC"]
    assert pa.ANNOTATION_PLAN_KEY not in by_asset["LMT"]
    assert by_asset["NOC"]["context_engines"] == ["government_revenue_foresight"]


def test_runtime_fingerprint_check_discards_an_annotation_pass_that_moved_a_decision(
    tmp_path: Path, monkeypatch,
) -> None:
    """The gate is enforced at RUNTIME, not only in this suite.

    A future edit that touches a decision field must degrade to "no annotation"
    rather than ship a moved number. Simulated by making the adapter's own
    fingerprint disagree with itself once the annotation is applied.
    """
    envelope = _envelope(tmp_path)
    calls: list[int] = []
    real = pa.decision_fingerprint

    def _drifting(plans):
        calls.append(1)
        # Second call is the post-annotation one; report a different value.
        return real(plans) if len(calls) < 2 else "moved"

    monkeypatch.setattr(pa, "decision_fingerprint", _drifting)
    annotated = pa.annotate_selected_plans(_plans(), envelope)

    assert all(pa.ANNOTATION_PLAN_KEY not in plan for plan in annotated)
    assert _decision_bytes(annotated) == _decision_bytes(_plans())


# --------------------------------------------------------------------------- #
# GATE 2 — timeouts and malformed packets fail open
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("envelope", "description"),
    [
        (None, "no envelope at all"),
        ({}, "empty mapping"),
        ({"annotations": []}, "no contract"),
        ({"contract": "something.else.v1", "annotations": []}, "wrong contract"),
        ({"contract": pa.CONTRACT, "annotations": []}, "no authority block"),
        ("not a mapping", "a string"),
        (42, "a number"),
    ],
)
def test_a_malformed_envelope_fails_open_to_prophets_decision(
    envelope, description: str
) -> None:
    baseline = _plans()

    annotated = pa.annotate_selected_plans(baseline, envelope)

    assert _decision_bytes(annotated) == _decision_bytes(baseline)
    assert all(pa.ANNOTATION_PLAN_KEY not in plan for plan in annotated)


def test_a_broken_authority_fence_fails_open(tmp_path: Path) -> None:
    """A partial fence is indistinguishable from no fence; both are refused."""
    for mutation in (
        lambda e: e["authority"].pop("can_rank"),
        lambda e: e["authority"].update({"can_rank": 0}),
        lambda e: e["authority"].update({"tier": "signal"}),
        lambda e: e["authority"].update({"context_only": False}),
        lambda e: e["annotations"][0]["authority"].update({"can_size": True}),
    ):
        envelope = _envelope(tmp_path)
        mutation(envelope)
        annotated = pa.annotate_selected_plans(_plans(), envelope)

        assert _decision_bytes(annotated) == _decision_bytes(_plans())
        assert all(pa.ANNOTATION_PLAN_KEY not in plan for plan in annotated)


def test_a_packet_builder_timeout_still_delivers_the_procurement_evidence(
    tmp_path: Path,
) -> None:
    """A timeout costs the shadow packet, not the annotation and not the decision.

    The procurement evidence is independently useful, so it ships with the reason
    named rather than being withheld because a market leg was slow.
    """
    def _timeout(_candidate):
        raise TimeoutError("neural web read exceeded its budget")

    envelope = pa.build_annotation_envelope(
        _queue(),
        selected_tickers=["NOC"],
        generated_at=GENERATED_AT,
        packet_builder=_timeout,
    )

    assert len(envelope["annotations"]) == 1
    annotation = envelope["annotations"][0]
    assert annotation["shadow_context"] is None
    assert annotation["shadow_context_reason_code"] == "shadow_packet_builder_failed"
    assert annotation["procurement_event"]["event_type"] == "obligation"
    annotated = pa.annotate_selected_plans(_plans(), envelope)
    assert _decision_bytes(annotated) == _decision_bytes(_plans())


def test_an_exhausted_time_budget_degrades_coverage_never_the_plan_list() -> None:
    """Budget exhaustion drops packets, not plans, and says so in coverage."""
    ticks = iter([0.0, 999.0, 999.0, 999.0])

    envelope = pa.build_annotation_envelope(
        _queue(),
        selected_tickers=["NOC"],
        generated_at=GENERATED_AT,
        packet_builder=lambda _c: {"packet_id": "grsp1-" + "a" * 24},
        time_budget_seconds=1.0,
        clock=lambda: next(ticks),
    )

    assert envelope["coverage"]["shadow_packet_budget_exhausted"] is True
    assert len(envelope["annotations"]) == 1
    assert envelope["annotations"][0]["shadow_context_reason_code"] == (
        "shadow_packet_time_budget_exhausted"
    )


def test_a_malformed_annotation_row_is_skipped_and_the_rest_survive(
    tmp_path: Path,
) -> None:
    envelope = _envelope(tmp_path)
    envelope["annotations"].append({"contract": "bogus.v1", "ticker": "NOC"})

    annotated = pa.annotate_selected_plans(_plans(), envelope)

    assert _decision_bytes(annotated) == _decision_bytes(_plans())
    attached = next(plan for plan in annotated if plan["asset"] == "NOC")
    assert len(attached[pa.ANNOTATION_PLAN_KEY]["annotations"]) == 1


def test_a_candidate_without_the_display_only_fence_is_never_annotated() -> None:
    """A candidate whose own authority is broken is skipped with a named reason."""
    queue = _queue()
    queue["candidates"][0]["authority"]["can_rank"] = True

    envelope = pa.build_annotation_envelope(
        queue, selected_tickers=["NOC"], generated_at=GENERATED_AT
    )

    assert envelope["annotations"] == []
    assert envelope["skipped"][0]["reason_code"] == (
        "candidate_not_traceable_or_not_display_only"
    )


def test_a_trade_flagged_candidate_is_refused_outright() -> None:
    """``is_neuralweb_trade_candidate`` must be exactly False, never merely falsy."""
    queue = _queue()
    queue["candidates"][0]["is_neuralweb_trade_candidate"] = True

    envelope = pa.build_annotation_envelope(
        queue, selected_tickers=["NOC"], generated_at=GENERATED_AT
    )

    assert envelope["annotations"] == []


def test_repo_entry_point_fails_open_when_the_queue_is_absent(tmp_path: Path) -> None:
    baseline = _plans()

    annotated = pa.annotate_plans_from_repo(
        baseline, repo_root=tmp_path, generated_at=GENERATED_AT
    )

    assert _decision_bytes(annotated) == _decision_bytes(baseline)
    assert all(pa.ANNOTATION_PLAN_KEY not in plan for plan in annotated)


@pytest.mark.parametrize(
    ("body", "description"),
    [
        ("not json at all", "unparseable"),
        ("[]", "not a mapping"),
        (json.dumps({"contract": "other.v1", "candidates": []}), "wrong contract"),
        (
            json.dumps({
                "contract": pa.QUEUE_CONTRACT,
                "candidates": [],
                "authority": {"tier": "display", "context_only": True},
            }),
            "partial authority fence",
        ),
    ],
)
def test_a_malformed_queue_artifact_is_refused_by_the_reader(
    body: str, description: str, tmp_path: Path
) -> None:
    path = tmp_path / pa.QUEUE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")

    assert pa.read_candidate_queue(tmp_path) is None


def test_the_committed_queue_artifact_is_readable_and_display_only() -> None:
    """Live probe: the real artifact the adapter reads in production."""
    queue = pa.read_candidate_queue(ROOT)

    assert queue is not None
    assert queue["contract"] == pa.QUEUE_CONTRACT
    assert pa.display_only_authority(queue["authority"])
    # Wave 9C's standing truth: the radar stays empty until a real post-baseline
    # eligible event exists, so the production annotation pass is a no-op today.
    assert queue["counts"]["total"] == len(queue["candidates"])


def test_the_committed_queue_annotates_nothing_and_moves_nothing() -> None:
    baseline = _plans()

    annotated = pa.annotate_plans_from_repo(
        baseline, repo_root=ROOT, generated_at=GENERATED_AT
    )

    assert _decision_bytes(annotated) == _decision_bytes(baseline)


# --------------------------------------------------------------------------- #
# GATE 3 — Prophet cannot call Government Revenue to source a candidate
# --------------------------------------------------------------------------- #

#: Modules that CREATE, project, or grade a Government Revenue candidate.  None
#: of them may appear anywhere on a Prophet module's import graph, at any depth.
CANDIDATE_SOURCE_MODULES = frozenset({
    "engine.government_revenue.candidates",
    "engine.government_revenue.candidate_grader",
    "engine.government_revenue.award_events",
    "engine.government_revenue.entity_resolution",
    "engine.government_revenue.issuer_graph_expansion",
    "engine.government_revenue.opportunities",
    "engine.government_revenue.workspace",
    "engine.government_revenue.dossiers",
    "engine.government_revenue.idv_dossiers",
    "engine.government_revenue.subaward_dossiers",
    "engine.government_revenue.budget_program",
    "engine.government_revenue.metrics",
    # Display-tier and non-authoritative, but it reads the IDV and prime-award
    # dossier rails and constructs new relationship evidence from exact source
    # identities.  Keep evidence builders on the source side of this boundary.
    "engine.government_revenue.idv_bridge",
    # A display-only evidence projection today, but it reads the recipient graph
    # and constructs a new Government Revenue rail from raw SBIR observations.
    # Keep it on the source side of this fail-closed boundary unless/until the
    # architecture gives non-candidate evidence builders their own class.
    "engine.government_revenue.sbir_progression",
})

#: The sanctioned annotate-only seam: selectors that may only decorate a row
#: another engine already admitted.
ANNOTATION_SEAM_MODULES = frozenset({
    "engine.government_revenue.federation",
    "engine.government_revenue.freshness",
    "engine.government_revenue.prophet_annotation",
    "engine.government_revenue.shadow_context",
    "engine.government_revenue.market_context",
    "engine.government_revenue.point_in_time",
    # Semantic labels/refusals only: this module cannot read observations or
    # construct a candidate and is safe on the annotate-only side.
    "engine.government_revenue.amount_semantics",
    # Display-only per-issuer identity projector (D2 Identity Atlas): exact-ID
    # graph traversal into its own artifact, no candidate mint/grade path and
    # no ledger/queue write — the candidate builder does not import it.
    "engine.government_revenue.identity_atlas",
})

def _prophet_modules() -> tuple[str, ...]:
    """Every Prophet module on disk, discovered rather than hand-listed.

    A hand-typed list narrows silently: ``engine/prophet_governor.py`` does not
    exist (it lives under ``engine/neuralweb/``), so naming it produced a SKIP
    that read as a pass. Globbing means a new Prophet module is covered the day
    it lands.
    """
    found = sorted(
        path.relative_to(ROOT).as_posix()
        for pattern in ("engine/prophet*.py", "engine/neuralweb/prophet*.py")
        for path in ROOT.glob(pattern)
    )
    assert "engine/prophet_bridge.py" in found, "the plan originator must be covered"
    return tuple(found)


PROPHET_MODULES = _prophet_modules()


def _module_imports(path: Path) -> set[str]:
    """Every module name imported by a file, including function-local imports.

    Function-local is deliberate: this repo defers heavy imports into call sites,
    so a scan restricted to module level would see almost nothing and pass
    unconditionally.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _module_path(module: str) -> Path | None:
    candidate = ROOT / (module.replace(".", "/") + ".py")
    return candidate if candidate.exists() else None


def _transitive_imports(start: Path, *, limit: int = 400) -> set[str]:
    """Walk the in-repo import graph from one file, following engine/lib modules."""
    seen_files = {start.resolve()}
    reached: set[str] = set()
    frontier = [start]
    while frontier and len(seen_files) < limit:
        current = frontier.pop()
        for name in _module_imports(current):
            reached.add(name)
            path = _module_path(name)
            if path is None or path.resolve() in seen_files:
                continue
            seen_files.add(path.resolve())
            frontier.append(path)
    return reached


@pytest.mark.parametrize("relative", PROPHET_MODULES)
def test_no_prophet_module_can_reach_a_govrev_candidate_source(relative: str) -> None:
    """The gate, over the TRANSITIVE graph.

    A direct-import check would pass while ``prophet_annotation`` quietly imported
    the queue builder one hop away — which is exactly why that module reads the
    artifact as JSON instead of calling ``is_valid_candidate_queue``.
    """
    path = ROOT / relative
    assert path.exists(), f"{relative} was discovered on disk and must still be there"

    reached = _transitive_imports(path)
    offenders = sorted(name for name in reached if name in CANDIDATE_SOURCE_MODULES)

    assert offenders == [], (
        f"{relative} can reach Government Revenue candidate sources {offenders}. "
        "Prophet may consume the annotate-only seam "
        f"({sorted(ANNOTATION_SEAM_MODULES)}) and nothing that mints a candidate."
    )


def test_the_annotation_adapter_itself_imports_no_candidate_source() -> None:
    """The adapter is the module most tempted to import the builder; it must not."""
    reached = _transitive_imports(ROOT / "engine/government_revenue/prophet_annotation.py")

    assert sorted(name for name in reached if name in CANDIDATE_SOURCE_MODULES) == []


def test_the_candidate_source_boundary_list_matches_the_lobe_on_disk() -> None:
    """A new govrev module must be classified, or this gate silently narrows.

    Without this, adding ``engine/government_revenue/new_source.py`` would leave
    it outside both sets and the boundary test above would not see it.
    """
    on_disk = {
        f"engine.government_revenue.{path.stem}"
        for path in (ROOT / "engine/government_revenue").glob("*.py")
        if path.stem != "__init__"
    }
    unclassified = sorted(on_disk - CANDIDATE_SOURCE_MODULES - ANNOTATION_SEAM_MODULES)

    assert unclassified == [], (
        f"unclassified Government Revenue modules {unclassified}: add each to "
        "CANDIDATE_SOURCE_MODULES (it can mint or grade a candidate) or to "
        "ANNOTATION_SEAM_MODULES (it can only decorate an admitted row)."
    )


def test_the_adapter_derives_its_universe_from_the_finished_plan_list(
    tmp_path: Path,
) -> None:
    """There is no path by which govrev influences WHICH names are selected.

    The only input naming a universe is the plan list itself, so an empty plan
    list must annotate nothing even with a queue full of candidates.
    """
    annotated = pa.annotate_plans_from_repo(
        [], repo_root=ROOT, generated_at=GENERATED_AT
    )
    assert annotated == []

    envelope = pa.build_annotation_envelope(
        _queue(), selected_tickers=[], generated_at=GENERATED_AT
    )
    assert envelope["annotations"] == []
    assert envelope["coverage"]["selected_ticker_count"] == 0


# --------------------------------------------------------------------------- #
# GATE 4 — authority remains display/context
# --------------------------------------------------------------------------- #


def test_annotation_authority_mirrors_the_committed_queue_authority_block() -> None:
    """Mirrored against the artifact on disk, not against a copy of my own constant."""
    committed = json.loads(
        (ROOT / "data/government_revenue/candidate_queue.json").read_text(encoding="utf-8")
    )

    assert pa.AUTHORITY == committed["authority"]


def test_every_authority_surface_in_the_envelope_is_display_only(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)

    assert pa.display_only_authority(envelope["authority"])
    for annotation in envelope["annotations"]:
        assert pa.display_only_authority(annotation["authority"])
        assert annotation["allowed_behavior"] == "annotate_only"
        assert annotation["shadow_context"]["authority"] == pa.AUTHORITY
    annotated = pa.annotate_selected_plans(_plans(), envelope)
    block = next(plan for plan in annotated if plan["asset"] == "NOC")[pa.ANNOTATION_PLAN_KEY]
    assert pa.display_only_authority(block["authority"])
    assert block["allowed_behavior"] == "annotate_only"


def test_the_envelope_carries_no_rank_size_or_gate_field(tmp_path: Path) -> None:
    """Shape gate: the record has nowhere to put a selection act."""
    envelope = _envelope(tmp_path)
    rendered = json.dumps(envelope["annotations"], sort_keys=True)

    for forbidden in ('"rank"', '"size"', '"gate"', '"conviction"', '"priority"', '"act_level"'):
        assert forbidden not in rendered


def test_label_is_shadow_context_bilingually(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)

    for annotation in envelope["annotations"]:
        assert annotation["label"] == {"en": "shadow context", "zh": "影子背景"}


# --------------------------------------------------------------------------- #
# GATE 5 — every rendered annotation traces to an exact generation
# --------------------------------------------------------------------------- #


def test_every_annotation_traces_to_the_exact_candidate_and_evidence_generation(
    tmp_path: Path,
) -> None:
    queue = _queue()
    candidate = queue["candidates"][0]
    envelope = pa.build_annotation_envelope(
        queue,
        selected_tickers=["NOC"],
        generated_at=GENERATED_AT,
        packet_builder=_packet_builder(tmp_path),
    )
    annotation = envelope["annotations"][0]

    assert annotation["candidate_id"] == candidate["candidate_id"]
    assert annotation["observation_id"] == candidate["observation_id"]
    assert annotation["generation"]["queue_content_id"] == queue["content_id"]
    assert annotation["generation"]["queue_source_generation_ids"] == sorted(
        set(queue["source_generation_ids"])
    )
    assert annotation["generation"]["shadow_packet_id"] == (
        annotation["shadow_context"]["packet_id"]
    )
    assert annotation["evidence_refs"]["artifact_content_ids"] == sorted(
        set(candidate["artifact_content_ids"])
    )
    assert annotation["evidence_refs"]["event_refs"] == sorted(set(candidate["event_refs"]))
    assert annotation["evidence_refs"]["receipt_refs"] == [
        row["ref_id"] for row in candidate["source_receipt_refs"]
    ]
    assert annotation["issuer"]["graph_digest"] == (
        candidate["issuer_resolution_ref"]["graph_digest"]
    )


def test_annotation_id_changes_when_the_generation_it_renders_changes(
    tmp_path: Path,
) -> None:
    """A rendered annotation must not keep its identity across a new generation."""
    first = _envelope(tmp_path)["annotations"][0]

    queue = _queue()
    queue["content_id"] = "grcq1-" + "f" * 24
    second = pa.build_annotation_envelope(
        queue,
        selected_tickers=["NOC"],
        generated_at=GENERATED_AT,
        packet_builder=_packet_builder(tmp_path),
    )["annotations"][0]

    assert first["annotation_id"] != second["annotation_id"]


def test_contradictions_reach_prophet_intact_and_unaveraged(tmp_path: Path) -> None:
    """Wave 9E's disagreements survive delivery with their handling promise."""
    from tests.test_government_revenue_shadow_context import _contradictory_legs

    def _build(candidate):
        return sc.build_shadow_packet(
            candidate, repo_root=tmp_path, legs_provider=_contradictory_legs
        )

    envelope = pa.build_annotation_envelope(
        _queue(), selected_tickers=["NOC"], generated_at=GENERATED_AT, packet_builder=_build
    )
    annotation = envelope["annotations"][0]

    assert annotation["contradictions"]
    assert all(
        row["handling"] == "both_legs_remain_visible_not_averaged"
        for row in annotation["contradictions"]
    )
    assert annotation["contradictions"] == [
        {
            "contradiction_id": row["contradiction_id"],
            "kind": row["kind"],
            "legs": sorted(row["legs"]),
            "handling": row["handling"],
            "statement_en": row["statement_en"],
            "statement_zh": row["statement_zh"],
        }
        for row in annotation["shadow_context"]["contradictions"]
    ]


def test_annotation_freshness_and_coverage_come_from_the_candidate_not_the_clock(
    tmp_path: Path,
) -> None:
    candidate = _queue()["candidates"][0]
    annotation = _envelope(tmp_path)["annotations"][0]

    assert annotation["known_at"] == candidate["known_at"]
    assert annotation["freshness"]["award_events_status"] == (
        candidate["freshness"]["award_events_status"]
    )
    assert annotation["coverage"]["exact_link_status"] == (
        candidate["coverage"]["exact_link_status"]
    )
    assert annotation["coverage"]["is_complete"] is False


def test_envelope_and_annotations_satisfy_the_published_contract(tmp_path: Path) -> None:
    envelope = _envelope(tmp_path)
    validator = _validator()

    validator.validate(envelope)
    for annotation in envelope["annotations"]:
        assert annotation["contract"] == pa.CONTRACT
        assert annotation["schema_version"] == pa.SCHEMA_VERSION


def test_envelope_contract_is_the_versioned_name_the_wave_specifies() -> None:
    assert pa.CONTRACT == "government_revenue.prophet_annotation.v1"


# --------------------------------------------------------------------------- #
# the wired seam — the gate held against the real plan originator
# --------------------------------------------------------------------------- #


def _write_standouts(root: Path) -> Path:
    """A minimal us_standouts artifact the real originator will admit."""
    path = root / "site" / "factordata" / "us_standouts.json"
    path.parent.mkdir(parents=True)

    def _buy(ticker: str, score: int, spot: float) -> dict:
        return {
            "ticker": ticker,
            "dir": "up",
            "conviction": {"score": score, "band": "neutral", "drivers": ["momentum"], "cautions": []},
            "entry_signal": {
                "act_level": 3,
                # Current Prophet admission is status/class based.  Keep this
                # integration fixture on an admitted class so the wired-seam
                # assertion cannot become vacuous as the originator evolves.
                "status": "partial",
                "spot": spot,
                "chase_above": spot + 1,
                "atr_pct": 2.0,
            },
            "hold": {"anchor": "2026-08-03", "invalidation": spot - 8},
        }

    path.write_text(
        json.dumps({
            "as_of": "2026-08-03",
            "staleness": {
                "price_through": "2026-08-03",
                "delayed": False,
                "unknown": False,
                "basis": "panel_majority",
                "inputs": {"panel": {"mixed_vintage": False}},
            },
            "gate_go": True,
            "buy": [_buy("NOC", 82, 610.0), _buy("LMT", 75, 500.0)],
        }),
        encoding="utf-8",
    )
    return path


def test_the_wired_seam_leaves_the_real_originators_decision_byte_identical(
    tmp_path: Path, monkeypatch,
) -> None:
    """The gate through ``prophet_bridge.originate_plans`` itself, adapter on/off.

    The unit gates above prove the adapter is inert; this proves the WIRING is —
    the seam could be correct and still be called in the wrong place.
    """
    from engine import prophet_bridge as pb

    standouts = _write_standouts(tmp_path)
    monkeypatch.setattr(pb, "_load_stage_tilt_inputs", lambda: None)
    monkeypatch.setattr(pb, "_load_price_history", lambda _ticker: None)
    monkeypatch.setattr(pb, "resolve_option", lambda **_kwargs: None)
    monkeypatch.setattr(pb, "_load_government_revenue_context", lambda _path, _asof=None: {})

    monkeypatch.setattr(pb, "_annotate_with_government_revenue", lambda plans, _asof: plans)
    baseline = pb.originate_plans(standouts, "2026-08-03", existing_ids=set(), thetadata_store=None)
    assert baseline, "the fixture must originate at least one plan"

    monkeypatch.undo()
    monkeypatch.setattr(pb, "_load_stage_tilt_inputs", lambda: None)
    monkeypatch.setattr(pb, "_load_price_history", lambda _ticker: None)
    monkeypatch.setattr(pb, "resolve_option", lambda **_kwargs: None)
    monkeypatch.setattr(pb, "_load_government_revenue_context", lambda _path, _asof=None: {})
    wired = pb.originate_plans(standouts, "2026-08-03", existing_ids=set(), thetadata_store=None)

    assert _decision_bytes(wired) == _decision_bytes(baseline)
    assert pa.decision_fingerprint(wired) == pa.decision_fingerprint(baseline)
    assert [plan["id"] for plan in wired] == [plan["id"] for plan in baseline]


def test_the_wired_seam_fails_open_when_the_adapter_raises(
    tmp_path: Path, monkeypatch,
) -> None:
    """An exploding adapter must cost the annotation, never the plans."""
    from engine import prophet_bridge as pb

    standouts = _write_standouts(tmp_path)
    monkeypatch.setattr(pb, "_load_stage_tilt_inputs", lambda: None)
    monkeypatch.setattr(pb, "_load_price_history", lambda _ticker: None)
    monkeypatch.setattr(pb, "resolve_option", lambda **_kwargs: None)
    monkeypatch.setattr(pb, "_load_government_revenue_context", lambda _path, _asof=None: {})
    monkeypatch.setattr(
        pa, "annotate_plans_from_repo", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    plans = pb.originate_plans(standouts, "2026-08-03", existing_ids=set(), thetadata_store=None)

    assert plans
    assert all(pa.ANNOTATION_PLAN_KEY not in plan for plan in plans)


def test_annotation_without_a_packet_still_satisfies_the_contract() -> None:
    """The null-packet path is the production path until a packet builder is wired."""
    envelope = pa.build_annotation_envelope(
        _queue(), selected_tickers=["NOC"], generated_at=GENERATED_AT
    )

    _validator().validate(envelope)
    assert envelope["annotations"][0]["shadow_context"] is None
    assert envelope["annotations"][0]["shadow_context_reason_code"] == (
        "no_shadow_packet_builder_supplied"
    )
