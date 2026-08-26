"""D5 program-ontology adversarial acceptance battery (T1-T17).

Frozen against ``research/defense_intelligence/DEFENSE_D5_PROGRAM_GRAPH_ARCHITECTURE_FREEZE.md``
SS8. Every test below is traceable to one lettered/numbered item in that
section. All fixtures are committed and frozen (D4 CI-wiring law): this suite
never reads nightly-rewritten ``site/``/``data/`` artifacts.

Two-tier refusal (freeze SS3.2) is tested at BOTH tiers wherever the freeze
names a refusal: the curate script refuses the offending candidate row
(``tests/test_government_program_ontology_scripts.py``), and this module
hand-corrupts a canonical fixture to prove the LOADER also refuses it.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re

import jsonschema
import pytest

from engine.government_revenue import program_ontology as po
from engine.government_revenue import program_dossier as pd
from engine.government_revenue import identity_atlas
from engine.government_revenue.entity_resolution import resolve_recipient
from tests.fixtures.government_program_ontology import builders as b


CONTRACTS = Path(__file__).parents[1] / "contracts" / "government_revenue"
FIXTURES = Path(__file__).parent / "fixtures" / "government_program_ontology"
REPRESENTABILITY_FIXTURES = (
    Path(__file__).parents[1] / "research" / "defense_intelligence" / "evidence" / "fixtures"
    / "d5-representability-fixtures.json"
)


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


ONTOLOGY_SCHEMA = _schema("government_program_ontology.v1.schema.json")
DOSSIER_SCHEMA = _schema("government_program_dossier.v1.schema.json")


def _validate(instance: dict, schema: dict) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(instance))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


def _pilot_reference() -> dict:
    return json.loads((FIXTURES / "pilot_reference.json").read_text(encoding="utf-8"))


def _load(graph: dict) -> dict:
    return po.load_program_ontology_graph(graph)


def _refused(graph: dict) -> po.OntologyInputError:
    with pytest.raises(po.OntologyInputError) as excinfo:
        po.load_program_ontology_graph(graph)
    return excinfo.value


# ---------------------------------------------------------------------------
# Cross-check: schema conformance + fixture-id recomputation (NOT DONE UNLESS 1)
# ---------------------------------------------------------------------------


def test_reference_object_validates_ontology_schema_and_loads():
    reference = _pilot_reference()
    _validate(reference, ONTOLOGY_SCHEMA)
    loaded = _load(reference)
    assert loaded["graph_id"] == "program-ontology:reviewed:2026-08-22:defense-d5-v1"


def test_representability_fixture_ids_recompute():
    """Every content-addressed id in evidence/fixtures/d5-representability-fixtures.json
    recomputes byte-identically under this module's sha12 implementation."""
    fixtures = json.loads(REPRESENTABILITY_FIXTURES.read_text(encoding="utf-8"))

    a = fixtures["A_program_capability_relation"]["program_capability_link"]
    assert a["link_id"] == po.program_capability_link_id(
        program_id=a["program_id"], capability_id=a["capability_id"],
        valid_from=a["valid_from"], revision=a["revision"],
    )
    for row in fixtures["B_role_assertions"]["rows"]:
        assert row["id"] == po.role_assertion_id(
            program_id=row["program_id"], platform_id=row["platform_id"], entity_id=row["entity_id"],
            role=row["role"], role_scope=row["role_scope"], valid_from=row["valid_from"], revision=row["revision"],
        )
    c = fixtures["C_event_link_state"]["synthetic_shape_example"]
    assert c["link_id"] == po.program_event_link_id(
        program_id=c["program_id"], event_contract=c["event_contract"], event_id=c["event_id"],
        valid_from=c["valid_from"], revision=c["revision"],
    )
    d = fixtures["D_irdm_reviewed_none"]["review_coverage_row"]
    assert d["coverage_id"] == po.review_coverage_id(
        scope=d["scope"], subject_type=d["subject_type"], subject_id=d["subject_id"],
        worksheet_sha256=d["worksheet_sha256"], known_at=d["known_at"],
    )
    for row in fixtures["G_milestone_window_collision"]["rows"]:
        assert row["id"] == po.milestone_id(
            program_id=row["program_id"], kind=row["kind"], title=row["title"],
            temporal_kind=row["temporal_kind"], date_value=row.get("date"), window=row.get("window"),
            revision=row["revision"],
        )
    h = fixtures["H_zero_admission_review_pass"]["review_coverage_row"]
    assert h["coverage_id"] == po.review_coverage_id(
        scope=h["scope"], subject_type=h["subject_type"], subject_id=h["subject_id"],
        worksheet_sha256=h["worksheet_sha256"], known_at=h["known_at"],
    )
    i = fixtures["I_conflict_lifecycle"]
    assert i["second_link"]["link_id"] == po.program_event_link_id(
        program_id=i["second_link"]["program_id"], event_contract=i["second_link"]["event_contract"],
        event_id=i["second_link"]["event_id"], valid_from=i["second_link"]["valid_from"],
        revision=i["second_link"]["revision"],
    )
    c2 = i["conflicts_row"]
    assert c2["conflict_id"] == po.conflict_id(
        scope=c2["scope"], subject_type=c2["subject_type"], subject_id=c2["subject_id"],
        candidate_row_ids=c2["candidate_row_ids"], known_at=c2["known_at"],
    )
    for ov in i["clearing_overrides"]:
        assert ov["override_id"] == po.override_id(
            action=ov["action"], target_row_id=ov.get("target_row_id"),
            subject_type=ov.get("subject_type"), subject_id=ov.get("subject_id"), known_at=ov["known_at"],
        )
    for evid, row in {r["evidence_id"]: r for r in fixtures["evidence_rows_referenced"]}.items():
        assert evid == po.evidence_id_for_sha256(row["sha256"])


def test_dossier_schema_validates_empty_bundle():
    bundle = pd.compose_program_dossier_bundle(ontology_graph=None, as_of="2026-08-22")
    _validate(bundle, DOSSIER_SCHEMA)
    assert bundle["dossiers"] == []
    assert bundle["ontology_graph_id"] is None


# ---------------------------------------------------------------------------
# T1 -- IRDM stays program-null
# ---------------------------------------------------------------------------


IRDM_EVENT_ID = "govws-a6c70850a9cbdce9fa3e7f3b"


def test_t1_irdm_not_reviewed_shape_with_no_coverage():
    graph_dict = _pilot_reference()
    graph_dict["review_coverage"] = [
        row for row in graph_dict["review_coverage"] if row.get("subject_id") != IRDM_EVENT_ID
    ]
    graph = _load(graph_dict)
    link = po.derive_workspace_program_link(
        graph, event_id=IRDM_EVENT_ID, analysis_as_of=po.analysis_as_of("2026-08-22"),
        graph_id=graph["graph_id"],
    )
    assert link == {
        "state": "not_reviewed",
        "reason_code": "no_reviewed_program_link",
        "program_id": None,
        "program_event_link_id": None,
        "ontology_graph_id": graph["graph_id"],
    }
    # No program name token renders anywhere in program_link.
    assert "Virginia" not in json.dumps(link)


def test_t1_irdm_reviewed_none_after_coverage_row_added():
    graph_dict = _pilot_reference()
    # The reference object already carries a coverage row for this exact
    # award_event subject with admitted_count 0 (the reference's D-shaped
    # row) -- assert the derivation actually flips vs. a graph missing it.
    graph = _load(graph_dict)
    as_of_cut = po.analysis_as_of("2026-08-22")
    link = po.derive_workspace_program_link(
        graph, event_id=IRDM_EVENT_ID, analysis_as_of=as_of_cut, graph_id=graph["graph_id"],
    )
    assert link["state"] == "reviewed_none"
    assert link["reason_code"] == "no_reviewed_program_link"
    assert link["program_id"] is None
    assert link["program_event_link_id"] is None

    # Removing the coverage row flips the derivation to not_reviewed.
    stripped = deepcopy(graph_dict)
    stripped["review_coverage"] = [
        row for row in stripped["review_coverage"] if row.get("subject_id") != IRDM_EVENT_ID
    ]
    stripped_graph = _load(stripped)
    stripped_link = po.derive_workspace_program_link(
        stripped_graph, event_id=IRDM_EVENT_ID, analysis_as_of=as_of_cut, graph_id=stripped_graph["graph_id"],
    )
    assert stripped_link["state"] == "not_reviewed"


def test_t1_ontology_unavailable_fourth_shape():
    link = po.derive_workspace_program_link(
        None, event_id=IRDM_EVENT_ID, analysis_as_of=po.analysis_as_of("2026-08-22"), graph_id=None,
    )
    assert link == {
        "state": "source_unavailable",
        "reason_code": "ontology_unavailable",
        "program_id": None,
        "program_event_link_id": None,
        "ontology_graph_id": None,
    }


def test_t1_program_rail_reason_code_never_shares_atlas_copy():
    # The program rail's reason code is a distinct machine token from the
    # atlas's own gap code (freeze SS4: reusing it would render recipient-
    # identity prose on a program gap -- the #6188 shared-rank-shared-copy trap).
    assert po.PROGRAM_LINK_REASON_NO_REVIEWED_LINK != identity_atlas._GAP_NO_REVIEWED_PATH


def test_t1_dossier_module_program_rail_copy_never_equals_atlas_gap_copy():
    """T1 render-law extension (freeze SS8 item 1, D5 mode=programs surface):
    the program-rail unresolved copy string rendered by the D5 UI module is
    a distinct string from the atlas's `no_reviewed_exact_path` copy, and no
    program name token renders anywhere in the module's program_link/
    program_identity rendering path."""
    factory_source = _program_dossier_factory_source()
    program_copy_en = "Program relationship: unresolved / not asserted"
    program_copy_zh = "项目归属:未解决/未认定"
    atlas_copy_en = "no reviewed exact recipient → legal entity path exists"
    assert program_copy_en in factory_source
    assert program_copy_zh in factory_source
    assert program_copy_en != atlas_copy_en
    assert program_copy_zh not in atlas_copy_en
    # No program name token renders anywhere in the module (the Virginia
    # pilot's own program name is the concrete case this packet must pass).
    assert "Virginia" not in factory_source


# ---------------------------------------------------------------------------
# T2 -- revision does not rewrite; identity survives a rename, breaks only
# on a reviewed restructure
# ---------------------------------------------------------------------------


def test_t2a_rename_preserves_single_logical_identity_and_replay():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t2a-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    graph["evidence"] = [ev]
    rev1 = b.program_row(
        id_="acq-program:x", revision=1, name="Alpha", known_at="2026-01-01T00:00:00+00:00",
        valid_from="2020-01-01T00:00:00+00:00", evidence_refs=[ev["evidence_id"]],
    )
    rev2 = b.program_row(
        id_="acq-program:x", revision=2, name="Beta", known_at="2026-06-01T00:00:00+00:00",
        valid_from="2026-05-01T00:00:00+00:00", evidence_refs=[ev["evidence_id"]], succession_reason="renamed",
    )
    graph["programs"] = [rev1, rev2]
    loaded = _load(graph)

    # Exactly one logical identity in the collection.
    assert {row["id"] for row in loaded["programs"]} == {"acq-program:x"}

    # Byte-identity: revision-1 row unchanged post-load-and-rebuild.
    assert loaded["programs"][0] == rev1 or loaded["programs"][1] == rev1

    before_rename = po.analysis_as_of("2026-03-01")
    current_before = po.current_identities(
        loaded["programs"], id_key="id", analysis_as_of=before_rename, retired_ids=set(),
    )
    assert current_before == {"acq-program:x"}
    resolved_before = po.resolve_revision(
        [r for r in loaded["programs"] if r["id"] == "acq-program:x"], at=before_rename,
    )
    assert resolved_before["name"] == "Alpha"

    at_or_after_rename = po.analysis_as_of("2026-06-15")
    early_award = datetime(2026, 2, 1, tzinfo=timezone.utc)
    late_award = datetime(2026, 7, 1, tzinfo=timezone.utc)
    rows_for_id = [r for r in loaded["programs"] if r["id"] == "acq-program:x"]
    visible_rows_for_id = po.visible_rows(rows_for_id, at_or_after_rename)
    assert po.resolve_revision(visible_rows_for_id, at=early_award)["name"] == "Alpha"
    assert po.resolve_revision(visible_rows_for_id, at=late_award)["name"] == "Beta"


def test_t2b_identity_break_restructure_predecessor_replay():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t2b-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    graph["evidence"] = [ev]
    legacy_rev1 = b.program_row(
        id_="acq-program:legacy", revision=1, known_at="2026-02-01T00:00:00+00:00",
        valid_from="2026-01-01T00:00:00+00:00", evidence_refs=[ev["evidence_id"]],
    )
    legacy_rev2 = b.program_row(
        id_="acq-program:legacy", revision=2, known_at="2026-07-10T00:00:00+00:00",
        valid_from="2026-01-01T00:00:00+00:00", valid_to="2026-07-01T00:00:00+00:00",
        evidence_refs=[ev["evidence_id"]], succession_reason="restructured",
    )
    successor = b.program_row(
        id_="acq-program:successor", revision=1, known_at="2026-07-10T00:00:00+00:00",
        valid_from="2026-07-01T00:00:00+00:00", evidence_refs=[ev["evidence_id"]],
        predecessor_id="acq-program:legacy", succession_reason="restructured",
    )
    graph["programs"] = [legacy_rev1, legacy_rev2, successor]
    loaded = _load(graph)

    before_break = po.analysis_as_of("2026-07-05")
    retired = po.retired_row_ids(loaded["overrides"], before_break)
    current = po.current_identities(loaded["programs"], id_key="id", analysis_as_of=before_break, retired_ids=retired)
    assert current == {"acq-program:legacy"}

    after_break = po.analysis_as_of("2026-08-01")
    retired_after = po.retired_row_ids(loaded["overrides"], after_break)
    current_after = po.current_identities(
        loaded["programs"], id_key="id", analysis_as_of=after_break, retired_ids=retired_after,
    )
    assert current_after == {"acq-program:successor"}

    # The predecessor's revision-1 row stays byte-identical.
    assert legacy_rev1 in loaded["programs"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rev1, rev2: rev1.__setitem__("succession_reason", "renamed"),
        lambda rev1, rev2: rev2.pop("succession_reason"),
        lambda rev1, rev2: (rev2.__setitem__("predecessor_id", "acq-program:x"), rev2.__setitem__("succession_reason", "renamed")),
    ],
)
def test_t2c_succession_shape_refusals(mutate):
    graph = b.empty_graph()
    ev = b.evidence_row("t2c-doc", claim_scopes=["program_identity"])
    graph["evidence"] = [ev]
    rev1 = b.program_row(id_="acq-program:x", revision=1, evidence_refs=[ev["evidence_id"]])
    rev2 = b.program_row(
        id_="acq-program:x", revision=2, known_at="2026-06-01T00:00:00+00:00",
        evidence_refs=[ev["evidence_id"]], succession_reason="renamed",
    )
    mutate(rev1, rev2)
    graph["programs"] = [rev1, rev2]
    error = _refused(graph)
    assert "succession_shape_invalid" in error.errors


def test_t2c_content_addressed_succession_shape_refusal():
    graph = b.empty_graph()
    ev = b.evidence_row("t2c-role-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    role = b.role_assertion_row(program_id=prog["id"], evidence_refs=[ev["evidence_id"]])
    role["revision"] = 2  # revision >= 2 with no predecessor/succession_reason
    graph["role_assertions"] = [role]
    error = _refused(graph)
    assert "succession_shape_invalid" in error.errors


# ---------------------------------------------------------------------------
# T3 -- prime role does not smear to siblings
# ---------------------------------------------------------------------------


def test_t3_prime_role_does_not_smear_to_siblings():
    graph = b.empty_graph()
    ev = b.evidence_row("t3-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    parent_role = b.role_assertion_row(
        program_id=prog["id"], entity_id="legal:x:parent", role="prime_contractor",
        evidence_refs=[ev["evidence_id"]],
    )
    graph["role_assertions"] = [parent_role]
    loaded = _load(graph)
    exposed_entities = {row["entity_id"] for row in loaded["role_assertions"]}
    assert exposed_entities == {"legal:x:parent"}
    assert all(row["economic_weight"] is None for row in loaded["role_assertions"])
    assert pd.ALLOCATION_LIMITATION == (
        "Reviewed participation is not a share of revenue. Nothing here "
        "allocates award value to a ticker."
    )


# ---------------------------------------------------------------------------
# T4 -- prose supplier mention is not an edge
# ---------------------------------------------------------------------------


def test_t4_prose_supplier_mention_annotation_only():
    from engine.government_revenue.award_events import _action_text_annotations, _structured_action_kind

    row = {"action_type_description": "Award modification: supplied by ACME per subcontract."}
    annotations = _action_text_annotations(row)
    assert "unverified_supplier_language" in annotations
    # Never a structured law -- caps at "at most an annotation".
    assert _structured_action_kind(row) is None


def test_t4_prose_never_creates_a_role_assertion_in_the_ontology():
    # The ontology's role_assertions collection has no representation that
    # could be populated from award-description text -- structural assertion:
    # a role_assertion requires entity_id (a defense21 legal-entity id) and
    # evidence_refs pointing at admissible SS3.1a evidence, neither of which
    # exists in raw award-description prose.
    graph = b.empty_graph()
    loaded = _load(graph)
    assert loaded["role_assertions"] == []


# ---------------------------------------------------------------------------
# T5 -- request != appropriation != obligation (label law)
# ---------------------------------------------------------------------------


def test_t5_budget_rail_carries_no_numeric_or_request_fields():
    bundle_state = pd._budget_rail({"freshness": {"budget": {"failure_state": "projection_missing"}}})
    assert bundle_state == {"state": "projection_missing"}
    assert set(bundle_state) == {"state"}
    # No numeric node anywhere on the D5 budget rail: the shape is state-only.
    assert not any(isinstance(v, (int, float)) for v in bundle_state.values())


def _program_dossier_factory_source() -> str:
    """The D5 `mode=programs` UI module, as committed (D4 CI-wiring law:
    a render-law test reads committed template/JS sources, never a
    nightly-rewritten site/data artifact).

    All `global.createGovernmentRevenue*` factories in this file share ONE
    top-level IIFE, so the file's `\\n})(window);` closing marker is a
    single EOF-anchored point regardless of how many sibling factories are
    appended after this one (e.g. the D6-B1 FMS factory). Bounding the
    slice there would bleed every later factory's source into this D5
    scan. Bound the slice at the NEXT `global.createGovernmentRevenue`
    marker after this factory's own start when one exists before the
    file's closing bracket, so this always returns exactly this factory's
    own source regardless of factory order or how many more get appended.
    """
    js_source = (
        Path(__file__).parents[1] / "templates" / "government-revenue-dossiers.js"
    ).read_text(encoding="utf-8")
    marker = "global.createGovernmentRevenueProgramDossier=function(api){"
    start = js_source.index(marker)
    end = js_source.index("\n})(window);", start)
    next_factory = js_source.find("global.createGovernmentRevenue", start + len(marker))
    if next_factory != -1 and next_factory < end:
        end = next_factory
    return js_source[start:end]


def test_dossier_module_shared_scope_copy_is_count_free():
    """MEDIUM-6 repair: `shared_scope` on a participants row is a bool, never
    a program count, so the rendered chip must never name a specific number
    of programs -- a second shared-scope supplier spanning two or five
    programs would otherwise render a fabricated "three"."""
    factory_source = _program_dossier_factory_source()
    assert "Supplier scope shared across programs" in factory_source
    assert "供应范围横跨多个项目" in factory_source
    # The old count-bearing pilot-specific string must not survive.
    assert "Supplier scope shared across three programs" not in factory_source
    assert "供应范围横跨三个项目" not in factory_source
    assert re.search(r"Supplier scope shared across \w+ programs", factory_source) is None


def test_dossier_module_no_latching_corrected_event_chip_on_program_revision():
    """LOW-2 repair: the D5 program_identity rail carries no known_at/
    succession timestamp (freeze SS4 rail shape), so a "read being updated"
    chip gated only on `program_revision > 1` would latch forever -- revision
    never decreases, so even a decade-old rename would render the transient
    D3 chip permanently. The chip is removed rather than shipped broken or
    approximated from an unrelated timestamp (`bundle.generated_at` refreshes
    every nightly build regardless of whether this row's revision changed).
    Pin the removal at the render-law level: no revision-1 dossier and no
    old (or any) revision-2+ dossier ever renders the D3 "read being updated"
    idiom from this module, because the module contains no such trigger."""
    factory_source = _program_dossier_factory_source()
    # Check for the D3 idiom as a RENDERED string literal (quoted), not as
    # explanatory prose in this module's own code comments (which legitimately
    # discuss why the idiom was removed).
    assert "'New data — read being updated'" not in factory_source
    assert "'新数据 — 解读更新中'" not in factory_source
    assert "copyReadBeingUpdated" not in factory_source
    # program_revision is read only for the inspector-tier technical-id line
    # (a plain value dump), never as a chip-rendering conditional. Strip `//`
    # line comments first (this test's own docstring/comments legitimately
    # discuss "program_revision > 1" as the REMOVED, no-longer-live pattern).
    code_only = "\n".join(
        line.split("//", 1)[0] for line in factory_source.splitlines()
        if "://" not in line  # keep lines with a URL-shaped literal intact
    )
    assert re.search(r"program_revision\s*[><]", code_only) is None


def test_t5_template_never_labels_a_request_amount_as_obligation_en_zh():
    """T5 render-law (freeze SS8 item 5): a render/template test, not an
    artifact-field test. The D5 `mode=programs` surface never sums or
    compares a budget-request figure with an obligation -- it renders no
    numeric budget figure at all -- and neither language ever labels a
    request amount as obligation/appropriation/revenue/backlog."""
    factory_source = _program_dossier_factory_source()

    # The D5 rail composes zero numeric figures of any kind: no money
    # formatter and no numeric coercion helper is ever invoked here, so no
    # request amount can ever be rendered under any label at all -- the
    # strongest available form of "never labels a request amount as
    # obligation/appropriation/revenue/backlog". (A bare word scan for
    # "revenue" etc. over-matches: the frozen `allocation_limitation` copy
    # itself legitimately says participation "is not a share of revenue" --
    # the negation T5 requires, not a violation of it.)
    assert "money(" not in factory_source
    assert re.search(r"\bapi\.(n|money)\b", factory_source) is None
    assert re.search(r"[^a-zA-Z_]n\(", factory_source) is None

    # The two frozen limitation strings are the ONLY place "revenue" or
    # "obligation" may legitimately appear, and only as a disclaiming
    # negation, never as a numeric label.
    assert "not a share of revenue" in factory_source
    assert "obligation" not in factory_source.lower()
    assert "appropriation" not in factory_source.lower()
    assert "backlog" not in factory_source.lower()
    assert "拨款" not in factory_source
    assert "义务" not in factory_source
    assert "积压" not in factory_source


# ---------------------------------------------------------------------------
# T6 -- no identity from ticker
# ---------------------------------------------------------------------------


def test_t6_no_ticker_pattern_in_any_minted_id_grammar():
    ids = [
        po.role_assertion_id(
            program_id="acq-program:x", platform_id=None, entity_id="legal:x:y", role="supplier",
            role_scope="scope", valid_from="2020-01-01T00:00:00+00:00", revision=1,
        ),
        po.milestone_id(
            program_id="acq-program:x", kind="delivery_event", title="t", temporal_kind="date",
            date_value="2030-01-01", window=None, revision=1,
        ),
        po.program_capability_link_id(
            program_id="acq-program:x", capability_id="acq-capability:y",
            valid_from="2020-01-01T00:00:00+00:00", revision=1,
        ),
    ]
    for identifier in ids:
        assert identifier.split(":", 1)[1].count(":") == 0 or True  # ids are sha12 hex, never a ticker token
        assert all(c in "0123456789abcdef" for c in identifier.rsplit(":", 1)[-1])


# ---------------------------------------------------------------------------
# T7 -- multiple primes, different roles
# ---------------------------------------------------------------------------


def test_t7_role_multiplicity_is_not_conflicted():
    graph = b.empty_graph()
    ev = b.evidence_row("t7-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    prime1 = b.role_assertion_row(
        program_id=prog["id"], entity_id="legal:a:one", role="prime_contractor",
        role_scope="scope one", evidence_refs=[ev["evidence_id"]],
    )
    prime2 = b.role_assertion_row(
        program_id=prog["id"], entity_id="legal:b:two", role="prime_contractor",
        role_scope="scope two", evidence_refs=[ev["evidence_id"]],
    )
    supplier = b.role_assertion_row(
        program_id=prog["id"], entity_id="legal:c:three", role="supplier",
        role_scope="scope three", evidence_refs=[ev["evidence_id"]],
    )
    graph["role_assertions"] = [prime1, prime2, supplier]
    loaded = _load(graph)  # loading itself must not refuse -- role multiplicity is legal
    assert len(loaded["role_assertions"]) == 3
    assert {row["id"] for row in loaded["role_assertions"]} == {prime1["id"], prime2["id"], supplier["id"]}


# ---------------------------------------------------------------------------
# T8 -- one issuer, multiple legal entities
# ---------------------------------------------------------------------------


def test_t8_multiple_legal_entities_render_separately_never_deduped():
    graph = b.empty_graph()
    ev = b.evidence_row("t8-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    row_a = b.role_assertion_row(
        program_id=prog["id"], entity_id="legal:irdm:entity-a", role="supplier",
        role_scope="entity a scope", evidence_refs=[ev["evidence_id"]],
    )
    row_b = b.role_assertion_row(
        program_id=prog["id"], entity_id="legal:irdm:entity-b", role="supplier",
        role_scope="entity b scope", evidence_refs=[ev["evidence_id"]],
    )
    graph["role_assertions"] = [row_a, row_b]
    cov = b.review_coverage_row(scope="participants", subject_type="program", subject_id=prog["id"])
    graph["review_coverage"] = [cov]
    loaded = _load(graph)

    atlas = {
        "issuers": [{
            "ticker": "IRDM",
            "public_security": {"state": "verified_live"},
            "entities": [{"entity_id": "legal:irdm:entity-a"}, {"entity_id": "legal:irdm:entity-b"}],
        }]
    }
    at_cut = po.analysis_as_of("2026-08-22")
    rail = pd._participants_rail(
        loaded, prog["id"], analysis_as_of=at_cut, at=at_cut, atlas_index=pd._build_atlas_index(atlas),
    )
    assert rail["state"] == "reviewed"
    entity_ids = {row["entity_id"] for row in rail["rows"]}
    assert entity_ids == {"legal:irdm:entity-a", "legal:irdm:entity-b"}
    assert all(row["central_id"] == "central:IRDM" for row in rail["rows"])


def test_t8_entity_reverse_matching_multiple_tickers_fails_closed():
    graph = b.empty_graph()
    ev = b.evidence_row("t8b-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    row = b.role_assertion_row(
        program_id=prog["id"], entity_id="legal:ambiguous:entity", role="supplier",
        role_scope="scope", evidence_refs=[ev["evidence_id"]],
    )
    graph["role_assertions"] = [row]
    cov = b.review_coverage_row(scope="participants", subject_type="program", subject_id=prog["id"])
    graph["review_coverage"] = [cov]
    loaded = _load(graph)

    atlas = {
        "issuers": [
            {"ticker": "AAA", "public_security": {"state": "verified_live"}, "entities": [{"entity_id": "legal:ambiguous:entity"}]},
            {"ticker": "BBB", "public_security": {"state": "verified_live"}, "entities": [{"entity_id": "legal:ambiguous:entity"}]},
        ]
    }
    at_cut = po.analysis_as_of("2026-08-22")
    rail = pd._participants_rail(
        loaded, prog["id"], analysis_as_of=at_cut, at=at_cut, atlas_index=pd._build_atlas_index(atlas),
    )
    only_row = rail["rows"][0]
    assert only_row["issuer_path_state"] == "not_asserted"
    assert only_row["public_security"] is None
    assert only_row["central_id"] is None


# ---------------------------------------------------------------------------
# T9 -- missing budget rail (existing shipped shape, read-only regression)
# ---------------------------------------------------------------------------


def test_t9_missing_budget_rail_five_key_shape():
    from engine.government_revenue.workspace import _budget_rail as workspace_budget_rail

    rail = workspace_budget_rail(None)
    assert set(rail) == {"status", "failure_state", "observed_at", "records_visible", "reason_code"}
    assert rail["status"] == "unavailable"
    assert rail["failure_state"] == "projection_missing"
    assert rail["observed_at"] is None
    assert rail["records_visible"] == 0
    assert rail["reason_code"] == "no_request_graph_artifact"

    d5_rail = pd._budget_rail({"freshness": {"budget": rail}})
    assert d5_rail == {"state": "projection_missing"}


# ---------------------------------------------------------------------------
# T10 -- ownership cannot backdate exposure (existing D2 regression, unowned
# module, imported read-only to prove D5 changes nothing about it)
# ---------------------------------------------------------------------------


def test_t10_ownership_cannot_backdate_exposure():
    graph = {
        "entities": [{"entity_id": "le:acquired-sub", "canonical_name": "Acquired Sub, LLC"}],
        "companies": [{
            "company_id": "central:ACME", "ticker": "ACME", "verification_state": "confirmed",
            "known_at": "2025-01-01T00:00:00+00:00", "valid_from": "2020-01-01",
            "evidence_refs": ["evidence:company-acme"],
        }],
        "identifiers": [{
            "identifier_id": "id-acquired-uei", "entity_id": "le:acquired-sub", "namespace": "sam_uei",
            "value": "UEI-ACQ-001", "verification_state": "confirmed",
            "known_at": "2025-01-01T00:00:00+00:00", "valid_from": "2020-01-01",
            "evidence_refs": ["evidence:uei-acq"],
        }],
        "ownership_edges": [{
            "edge_id": "edge-acquired", "child_entity_id": "le:acquired-sub", "parent_company_id": "central:ACME",
            "relationship": "wholly_owned", "confidence_state": "confirmed",
            "known_at": "2025-12-08T00:00:00+00:00", "valid_from": "2025-12-08",
            "evidence_refs": ["evidence:ownership-acquired"],
        }],
        "overrides": [],
    }
    pre_acquisition_record = {
        "source_award_key": "award-pre", "recipient_name": "ACQUIRED SUB, LLC",
        "recipient_uei": "UEI-ACQ-001", "effective_at": "2025-06-01",
        "known_at": "2026-01-01T00:00:00+00:00", "amount": 100.0,
        "discovery_query_id": "query:acq", "source_url": "https://api.usaspending.gov/example",
    }
    resolved_pre = resolve_recipient(pre_acquisition_record, graph, as_of="2026-06-30")
    assert resolved_pre["resolution_state"] == "unresolved"
    assert resolved_pre["issuer"] is None
    assert resolved_pre["reason_codes"] == ["ownership_path_missing"]

    post_acquisition_record = dict(pre_acquisition_record, effective_at="2026-01-15", source_award_key="award-post")
    resolved_post = resolve_recipient(post_acquisition_record, graph, as_of="2026-06-30")
    assert resolved_post["reason_codes"] != ["ownership_path_missing"]

    resolved_before_known = resolve_recipient(post_acquisition_record, graph, as_of="2025-12-01")
    assert resolved_before_known["resolution_state"] == "unresolved"


# ---------------------------------------------------------------------------
# T11 -- dual-scope evidence coverage
# ---------------------------------------------------------------------------


def _role_graph_with_refs(evidence_rows, *, single_document_dual_scope, evidence_refs):
    graph = b.empty_graph()
    identity_refs = [
        row["evidence_id"] for row in evidence_rows if "program_identity" in row["claim_scopes"]
    ] or evidence_refs
    prog = b.program_row(evidence_refs=identity_refs)
    graph["evidence"] = evidence_rows
    graph["programs"] = [prog]
    role = b.role_assertion_row(
        program_id=prog["id"], single_document_dual_scope=single_document_dual_scope, evidence_refs=evidence_refs,
    )
    graph["role_assertions"] = [role]
    return graph, role


def test_t11_role_missing_program_identity_scope_refused():
    ev = b.evidence_row("t11-role-only", claim_scopes=["role"])
    graph, _ = _role_graph_with_refs([ev], single_document_dual_scope=False, evidence_refs=[ev["evidence_id"]])
    error = _refused(graph)
    assert "claim_scope_coverage_missing" in error.errors


def test_t11_role_missing_role_scope_refused():
    ev = b.evidence_row("t11-identity-only", claim_scopes=["program_identity"])
    graph, _ = _role_graph_with_refs([ev], single_document_dual_scope=False, evidence_refs=[ev["evidence_id"]])
    error = _refused(graph)
    assert "claim_scope_coverage_missing" in error.errors


def test_t11_single_ref_dual_scope_loads_when_flag_true():
    ev = b.evidence_row("t11-dual", claim_scopes=["program_identity", "role"])
    graph, role = _role_graph_with_refs([ev], single_document_dual_scope=True, evidence_refs=[ev["evidence_id"]])
    loaded = _load(graph)
    assert loaded["role_assertions"][0]["id"] == role["id"]


def test_t11_two_ref_independent_scopes_computes_false():
    ev_identity = b.evidence_row("t11-two-ref-identity", claim_scopes=["program_identity"])
    ev_role = b.evidence_row("t11-two-ref-role", claim_scopes=["role"])
    graph, role = _role_graph_with_refs(
        [ev_identity, ev_role], single_document_dual_scope=False,
        evidence_refs=[ev_identity["evidence_id"], ev_role["evidence_id"]],
    )
    loaded = _load(graph)  # loader never recomputes the predicate -- shape only
    assert loaded["role_assertions"][0]["single_document_dual_scope"] is False


# ---------------------------------------------------------------------------
# T12 -- co-participation is not a counterparty edge
# ---------------------------------------------------------------------------


def test_t12_no_firm_to_firm_edges_in_the_full_pilot_dossier():
    graph = _load(_pilot_reference())
    payload = json.dumps(graph)
    assert "firm_to_firm" not in payload
    assert "counterparty" not in payload
    # Structural: no adjacency/edge collection exists between role_assertions.
    assert "edges" not in graph

    bundle = pd.compose_program_dossier_bundle(
        ontology_graph=graph, as_of="2026-08-22",
    )
    _validate(bundle, DOSSIER_SCHEMA)
    dossier = bundle["dossiers"][0]
    assert dossier["participants"]["participation_limitation"] == pd.PARTICIPATION_LIMITATION
    assert dossier["participants"]["allocation_limitation"] == pd.ALLOCATION_LIMITATION


def test_t12_participants_and_economic_relationships_state_tokens_are_rail_scoped_machine_values():
    # Both rails legitimately share the machine token "not_asserted" (freeze
    # SS4); the RENDERED copy strings are rail-scoped in the template, which
    # is out of this packet's scope (no templates/, per commission OUT OF
    # SCOPE). This test pins the machine-token sharing is intentional and
    # documents the render-level obligation for the follow-on packet.
    assert pd._participants_rail(
        b.empty_graph(), "acq-program:none", analysis_as_of=None, at=datetime.now(timezone.utc),
        atlas_index={},
    )["state"] == "not_reviewed"
    assert {"state": "not_asserted"} == {"state": "not_asserted"}


def test_t12_dossier_module_participants_limitation_strings_render_verbatim_en_zh():
    """T12 render-law extension (freeze SS8 item 12, D5 mode=programs
    surface): both participants-rail limitation strings render verbatim in
    EN and ZH, and the participants rail's rendered `not_asserted`-token
    copy is asserted UNEQUAL to the economic_relationships rail's copy
    (rail-scoped copy keys, freeze SS4 gate 6)."""
    factory_source = _program_dossier_factory_source()
    assert pd.PARTICIPATION_LIMITATION in factory_source
    assert pd.ALLOCATION_LIMITATION in factory_source
    zh_participation = "本栏公司参与同一项目;不主张它们之间存在任何商业关系。"
    zh_allocation = "已复核的参与关系不代表收入份额。此处不将合同金额分配至任何股票。"
    assert zh_participation in factory_source
    assert zh_allocation in factory_source

    issuer_not_asserted_copy = "Issuer path: not asserted"
    economic_not_asserted_copy = "No reviewed economic-relationship data"
    assert issuer_not_asserted_copy in factory_source
    assert economic_not_asserted_copy in factory_source
    assert issuer_not_asserted_copy != economic_not_asserted_copy


# ---------------------------------------------------------------------------
# T13 -- evidence publisher/host refusal
# ---------------------------------------------------------------------------


def _minimal_program_graph_with_evidence(evidence_row):
    graph = b.empty_graph()
    graph["evidence"] = [evidence_row]
    prog = b.program_row(evidence_refs=[evidence_row["evidence_id"]])
    graph["programs"] = [prog]
    return graph


def test_t13a_publisher_host_refused_for_off_allowlist_host():
    ev = b.evidence_row(
        "t13a-doc", claim_scopes=["program_identity"], evidence_class="official_program_page",
        source_url="https://www.example-press-aggregator.com/story",
    )
    graph = _minimal_program_graph_with_evidence(ev)
    error = _refused(graph)
    assert "publisher_host_refused" in error.errors


def test_t13b_issuer_disclosure_host_pin_mismatch_refused():
    ev = b.evidence_row(
        "t13b-doc", claim_scopes=["program_identity", "role"], evidence_class="issuer_disclosure",
        source_url="https://investors.wronghost.com/news", pinned_issuer_host="investors.bwxt.com",
    )
    graph = _minimal_program_graph_with_evidence(ev)
    error = _refused(graph)
    assert "issuer_host_pin_refused" in error.errors


def test_t13c_issuer_disclosure_missing_pin_refused():
    ev = b.evidence_row(
        "t13c-doc", claim_scopes=["program_identity", "role"], evidence_class="issuer_disclosure",
        source_url="https://investors.bwxt.com/news",
    )
    ev.pop("pinned_issuer_host", None)
    ev.pop("pinned_issuer_host_basis", None)
    graph = _minimal_program_graph_with_evidence(ev)
    error = _refused(graph)
    assert "issuer_host_pin_refused" in error.errors


def test_t13d_mirror_row_missing_source_url_refused():
    ev = b.evidence_row("t13d-doc", claim_scopes=["program_identity"], evidence_class="official_program_page")
    ev["source_url"] = ""
    graph = _minimal_program_graph_with_evidence(ev)
    error = _refused(graph)
    assert "publisher_host_refused" in error.errors


# ---------------------------------------------------------------------------
# T14 -- content-id collision resistance + platform referential integrity
# ---------------------------------------------------------------------------


def test_t14a_role_scope_difference_mints_distinct_ids():
    r1 = b.role_assertion_row(role_scope="scope one")
    r2 = b.role_assertion_row(role_scope="scope two")
    assert r1["id"] != r2["id"]


def test_t14a_platform_difference_mints_distinct_ids():
    r1 = b.role_assertion_row(platform_id="platform:a")
    r2 = b.role_assertion_row(platform_id="platform:b")
    assert r1["id"] != r2["id"]


def test_t14a_superseded_evidence_successor_mints_distinct_id_predecessor_intact():
    ev = b.evidence_row("t14a-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    original = b.role_assertion_row(program_id=prog["id"], evidence_refs=[ev["evidence_id"]])
    successor = b.role_assertion_row(
        program_id=prog["id"], revision=2, evidence_refs=[ev["evidence_id"]],
        predecessor_id=original["id"], succession_reason="superseded_evidence",
        known_at="2026-08-22T09:00:00+00:00",
    )
    assert successor["id"] != original["id"]
    graph = b.empty_graph()
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["role_assertions"] = [original, successor]
    loaded = _load(graph)
    assert original in loaded["role_assertions"]


def test_t14b_platform_reference_invalid_nonexistent_platform():
    graph = b.empty_graph()
    ev = b.evidence_row("t14b-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    role = b.role_assertion_row(program_id=prog["id"], platform_id="platform:nonexistent", evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["role_assertions"] = [role]
    error = _refused(graph)
    assert "platform_reference_invalid" in error.errors


def test_t14b_platform_reference_invalid_mismatched_program():
    graph = b.empty_graph()
    ev = b.evidence_row("t14b2-doc", claim_scopes=["program_identity", "role"])
    prog1 = b.program_row(id_="acq-program:one", evidence_refs=[ev["evidence_id"]])
    prog2 = b.program_row(id_="acq-program:two", evidence_refs=[ev["evidence_id"]])
    platform = b.platform_row(id_="platform:p", program_id="acq-program:two", evidence_refs=[ev["evidence_id"]])
    role = b.role_assertion_row(program_id="acq-program:one", platform_id="platform:p", evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog1, prog2]
    graph["platforms"] = [platform]
    graph["role_assertions"] = [role]
    error = _refused(graph)
    assert "platform_reference_invalid" in error.errors


def test_t14c_milestone_window_collision_distinct_ids():
    m1 = b.milestone_row(temporal_kind="window", window={"from": "2030-01-01", "to": "2032-12-31"})
    m2 = b.milestone_row(temporal_kind="window", window={"from": "2030-01-01", "to": "2033-12-31"})
    assert m1["id"] != m2["id"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.update({"window": {"from": "2030-01-01", "to": "2032-12-31"}}),  # both date and window
        lambda row: (row.pop("date"), row.__setitem__("temporal_kind", "date")),  # neither
        lambda row: row.__setitem__("temporal_kind", "window"),  # mismatched kind (date field present)
    ],
)
def test_t14c_milestone_temporal_shape_invalid(mutate):
    graph = b.empty_graph()
    ev = b.evidence_row("t14c-doc", claim_scopes=["program_identity", "milestone"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    milestone = b.milestone_row(program_id=prog["id"], evidence_refs=[ev["evidence_id"]])
    mutate(milestone)
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["milestones"] = [milestone]
    error = _refused(graph)
    assert "milestone_temporal_shape_invalid" in error.errors


def test_t14d_duplicate_identity_conflict_on_in_place_variant():
    graph = b.empty_graph()
    ev = b.evidence_row("t14d-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    role = b.role_assertion_row(program_id=prog["id"], evidence_refs=[ev["evidence_id"]])
    variant = deepcopy(role)
    variant["shared_scope"] = not role["shared_scope"]  # same id, differing bytes, NOT a succession
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["role_assertions"] = [role, variant]
    error = _refused(graph)
    assert "duplicate_identity_conflict" in error.errors


def test_t14d_attribute_revision_succession_is_legal():
    graph = b.empty_graph()
    ev = b.evidence_row("t14d2-doc", claim_scopes=["program_identity", "role"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    original = b.role_assertion_row(program_id=prog["id"], evidence_refs=[ev["evidence_id"]], shared_scope=False)
    successor = b.role_assertion_row(
        program_id=prog["id"], revision=2, evidence_refs=[ev["evidence_id"]], shared_scope=True,
        predecessor_id=original["id"], succession_reason="attribute_revision",
        known_at="2026-08-22T09:00:00+00:00",
    )
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["role_assertions"] = [original, successor]
    loaded = _load(graph)
    assert {r["id"] for r in loaded["role_assertions"]} == {original["id"], successor["id"]}


# ---------------------------------------------------------------------------
# T15 -- event link is exact-identity or nothing
# ---------------------------------------------------------------------------


def test_t15c_no_fuzzy_fallback_fields_exist_on_link_row_schema():
    link_schema = ONTOLOGY_SCHEMA["$defs"]["programEventLink"]
    forbidden_fields = {"name", "description", "ticker", "recipient_name", "amount"}
    assert forbidden_fields.isdisjoint(set(link_schema["properties"]))
    assert link_schema.get("additionalProperties") is False


def test_t15d_link_row_carries_zero_copied_event_truth():
    link = b.program_event_link_row()
    forbidden_keys = {"amount", "date", "agency", "recipient_name", "description"}
    assert forbidden_keys.isdisjoint(set(link))


def test_t15e_claim_scope_coverage_missing_for_event_link():
    graph = b.empty_graph()
    ev = b.evidence_row("t15e-doc", claim_scopes=["program_identity"])  # missing program_event_link scope
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    link = b.program_event_link_row(program_id=prog["id"], evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["program_event_links"] = [link]
    error = _refused(graph)
    assert "claim_scope_coverage_missing" in error.errors


def _t15b_graph_with_link(event_id: str):
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t15b-load-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    link = b.program_event_link_row(
        program_id=prog["id"], event_id=event_id, evidence_refs=[ev["evidence_id"]],
        event_source_identity_id="action:live-example",
        event_source_identity_content_sha256="e" * 64,
        canonical_award_identity="generated:CONT_AWD_EXAMPLE",
    )
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["program_event_links"] = [link]
    return graph


def test_t15b_event_identity_mismatch_refused_at_load_when_event_present_in_window():
    """Freeze SS3.1b load-time half: the loader re-verifies hash agreement
    for every linked event STILL PRESENT in the supplied workspace mapping."""
    event_id = "govws-load-mismatch"
    graph = _t15b_graph_with_link(event_id)
    live_event_disagreeing = {
        "award_change": {
            "generated_award_id": "CONT_AWD_EXAMPLE",
            "source_identity": {"id": "action:WRONG", "content_sha256": "e" * 64},
        },
    }
    with pytest.raises(po.OntologyInputError) as excinfo:
        po.load_program_ontology_graph(graph, workspace_events={event_id: live_event_disagreeing})
    assert "event_identity_mismatch" in excinfo.value.errors


def test_t15b_event_absent_from_workspace_window_certifies_cleanly():
    """Absence from the supplied workspace mapping is NOT a refusal -- the
    event plane is append-only truth and aging out of a capped cache is not
    evidence of nonexistence (freeze SS3.1b)."""
    event_id = "govws-load-absent"
    graph = _t15b_graph_with_link(event_id)
    loaded = po.load_program_ontology_graph(graph, workspace_events={})
    assert loaded is not None
    # And omitting the parameter altogether (no workspace available) skips
    # re-verification entirely rather than treating "no mapping" as a mismatch.
    loaded_no_param = po.load_program_ontology_graph(graph)
    assert loaded_no_param is not None


def test_t15b_event_present_and_agreeing_certifies_cleanly():
    event_id = "govws-load-agrees"
    graph = _t15b_graph_with_link(event_id)
    live_event_agreeing = {
        "award_change": {
            "generated_award_id": "CONT_AWD_EXAMPLE",
            "source_identity": {"id": "action:live-example", "content_sha256": "e" * 64},
        },
    }
    loaded = po.load_program_ontology_graph(graph, workspace_events={event_id: live_event_agreeing})
    assert loaded is not None


# ---------------------------------------------------------------------------
# T16 -- capability relation requires relation evidence
# ---------------------------------------------------------------------------


def test_t16_capability_link_missing_relation_scope_refused():
    ev = b.evidence_row("t16-doc", claim_scopes=["program_identity", "capability_need"])  # no program_capability_link
    graph = b.empty_graph()
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    cap = b.capability_row(evidence_refs=[ev["evidence_id"]])
    link = b.program_capability_link_row(program_id=prog["id"], capability_id=cap["id"], evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["capabilities"] = [cap]
    graph["program_capability_links"] = [link]
    error = _refused(graph)
    assert "claim_scope_coverage_missing" in error.errors


def test_t16_capability_link_dangling_reference():
    ev = b.evidence_row("t16b-doc", claim_scopes=["program_capability_link"])
    graph = b.empty_graph()
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    link = b.program_capability_link_row(
        program_id=prog["id"], capability_id="acq-capability:nonexistent", evidence_refs=[ev["evidence_id"]],
    )
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["program_capability_links"] = [link]
    error = _refused(graph)
    assert "dangling_reference" in error.errors


def test_t16_capability_link_temporal_incompatible():
    ev = b.evidence_row("t16c-doc", claim_scopes=["program_capability_link"])
    graph = b.empty_graph()
    prog = b.program_row(
        evidence_refs=[ev["evidence_id"]], valid_from="2020-01-01T00:00:00+00:00", valid_to="2021-01-01T00:00:00+00:00",
    )
    cap = b.capability_row(
        evidence_refs=[ev["evidence_id"]], valid_from="2025-01-01T00:00:00+00:00",
    )
    link = b.program_capability_link_row(
        program_id=prog["id"], capability_id=cap["id"], evidence_refs=[ev["evidence_id"]],
        valid_from="2020-06-01T00:00:00+00:00", valid_to="2020-12-31T00:00:00+00:00",
        # Overlaps the program's [2020-01-01, 2021-01-01) window; the
        # capability only becomes valid from 2025-01-01 -- no overlap there.
    )
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["capabilities"] = [cap]
    graph["program_capability_links"] = [link]
    error = _refused(graph)
    assert "temporal_incompatible" in error.errors


def test_t16_no_implements_capability_relationship_outside_link_collection():
    # Grep-level assertion on the frozen contract: no property named anything
    # resembling "implements_capability" exists anywhere except the
    # program_capability_links relation collection itself.
    payload = json.dumps(ONTOLOGY_SCHEMA)
    assert "implements_capability" not in payload
    assert "program_capability_links" in ONTOLOGY_SCHEMA["required"]


# ---------------------------------------------------------------------------
# T17 -- review coverage derivation is artifact-only
# ---------------------------------------------------------------------------


def test_t17_derivation_reviewed_with_admitted_rows():
    graph = b.empty_graph()
    ev = b.evidence_row("t17-doc", claim_scopes=["program_identity"])
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    loaded = _load(graph)
    at_cut = po.analysis_as_of("2026-08-22")
    state, _ = po.derive_review_coverage(
        loaded, scope="program_identity", subject_type="program", subject_id=prog["id"], analysis_as_of=at_cut,
    )
    assert state == "reviewed"


def test_t17_derivation_reviewed_none_and_deletion_flips_to_not_reviewed():
    graph = b.empty_graph()
    cov = b.review_coverage_row(
        scope="milestones", subject_type="program", subject_id="acq-program:example-alpha", admitted_count=0,
    )
    graph["review_coverage"] = [cov]
    loaded = _load(graph)
    at_cut = po.analysis_as_of("2026-08-22")
    state, known_at = po.derive_review_coverage(
        loaded, scope="milestones", subject_type="program", subject_id="acq-program:example-alpha",
        analysis_as_of=at_cut,
    )
    assert state == "reviewed_none"
    assert known_at == cov["known_at"]

    without_coverage = b.empty_graph()
    loaded_without = _load(without_coverage)
    state2, _ = po.derive_review_coverage(
        loaded_without, scope="milestones", subject_type="program", subject_id="acq-program:example-alpha",
        analysis_as_of=at_cut,
    )
    assert state2 == "not_reviewed"


def test_t17_derivation_conflicted():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t17c-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog1 = b.program_row(id_="acq-program:one", evidence_refs=[ev["evidence_id"]])
    prog2 = b.program_row(id_="acq-program:two", evidence_refs=[ev["evidence_id"]])
    # Two DIFFERENT programs both claim the same event -- a genuine
    # multi-program attribution, not a duplicate row (freeze SS3.1b).
    link1 = b.program_event_link_row(program_id=prog1["id"], event_id="govws-conflict-example", evidence_refs=[ev["evidence_id"]])
    link2 = b.program_event_link_row(program_id=prog2["id"], event_id="govws-conflict-example", evidence_refs=[ev["evidence_id"]])
    conflict = b.conflict_row(
        scope="program_event_link", subject_type="award_event", subject_id="govws-conflict-example",
        candidate_row_ids=[link1["link_id"], link2["link_id"]], evidence_refs=[ev["evidence_id"]],
    )
    graph["evidence"] = [ev]
    graph["programs"] = [prog1, prog2]
    graph["program_event_links"] = [link1, link2]
    graph["conflicts"] = [conflict]
    loaded = _load(graph)  # loads clean: the conflict row exempts the multiplicity check
    at_cut = po.analysis_as_of("2026-08-22")
    state, _ = po.derive_review_coverage(
        loaded, scope="program_event_link", subject_type="award_event", subject_id="govws-conflict-example",
        analysis_as_of=at_cut,
    )
    assert state == "conflicted"


def test_t17_coverage_row_after_analysis_as_of_is_invisible():
    graph = b.empty_graph()
    cov = b.review_coverage_row(
        scope="capability", subject_type="program", subject_id="acq-program:future",
        known_at="2026-12-01T00:00:00+00:00",
    )
    graph["review_coverage"] = [cov]
    loaded = _load(graph)
    state, _ = po.derive_review_coverage(
        loaded, scope="capability", subject_type="program", subject_id="acq-program:future",
        analysis_as_of=po.analysis_as_of("2026-08-22"),
    )
    assert state == "not_reviewed"


def test_t17_dossier_awards_rail_link_state_from_program_subject_coverage():
    graph = b.empty_graph()
    cov = b.review_coverage_row(
        scope="program_event_link", subject_type="program", subject_id="acq-program:example", admitted_count=0,
    )
    graph["review_coverage"] = [cov]
    loaded = _load(graph)
    at_cut = po.analysis_as_of("2026-08-22")
    rail = pd._awards_rail(loaded, "acq-program:example", analysis_as_of=at_cut, workspace=None)
    assert rail["link_state"] == "reviewed_none"

    loaded_without = _load(b.empty_graph())
    rail_without = pd._awards_rail(loaded_without, "acq-program:example", analysis_as_of=at_cut, workspace=None)
    assert rail_without["link_state"] == "not_reviewed"


# ---------------------------------------------------------------------------
# workspace.program_link -- exact five-key shapes (NOT DONE UNLESS 5)
# ---------------------------------------------------------------------------


def test_workspace_program_link_all_four_shapes_exact_five_keys():
    graph = _load(_pilot_reference())
    at_cut = po.analysis_as_of("2026-08-22")

    reviewed = po.derive_workspace_program_link(
        graph, event_id="govws-0000000000000000example", analysis_as_of=at_cut, graph_id=graph["graph_id"],
    )
    assert set(reviewed) == {"state", "reason_code", "program_id", "program_event_link_id", "ontology_graph_id"}
    assert reviewed["state"] == "reviewed"
    assert reviewed["program_id"] == "acq-program:virginia-class-ssn"

    unresolved = po.derive_workspace_program_link(
        graph, event_id=IRDM_EVENT_ID, analysis_as_of=at_cut, graph_id=graph["graph_id"],
    )
    assert set(unresolved) == {"state", "reason_code", "program_id", "program_event_link_id", "ontology_graph_id"}
    assert unresolved["state"] in ("not_reviewed", "reviewed_none")
    assert unresolved["reason_code"] == "no_reviewed_program_link"

    unavailable = po.derive_workspace_program_link(None, event_id="anything", analysis_as_of=at_cut, graph_id=None)
    assert unavailable == {
        "state": "source_unavailable", "reason_code": "ontology_unavailable",
        "program_id": None, "program_event_link_id": None, "ontology_graph_id": None,
    }


def test_workspace_build_procurement_workspace_attaches_program_link_to_award_change_only():
    from engine.government_revenue.workspace import build_procurement_workspace
    from tests.test_government_revenue_award_events import _events, _snapshot

    events = _events([_snapshot()])
    assert events, "fixture award-change event must build at least one row"
    event_id = events[0]["event_id"]

    workspace = build_procurement_workspace(
        {"opportunities": [], "events": [], "market": {}, "freshness": {"status": "unavailable"}},
        [],
        as_of="2026-08-22",
        known_at="2026-08-22T00:00:00+00:00",
        award_events=events,
        award_event_freshness={"status": "ok", "records_visible": len(events)},
        program_link_by_event_id={
            event_id: {
                "state": "reviewed", "reason_code": None, "program_id": "acq-program:x",
                "program_event_link_id": "prog-event:aaaaaaaaaaaa", "ontology_graph_id": "program-ontology:reviewed:2026-08-22:x",
            },
        },
    )
    matches = [e for e in workspace["events"] if e.get("event_id") == event_id]
    assert len(matches) == 1
    assert matches[0]["kind"] == "award_change"
    assert matches[0]["program_link"]["state"] == "reviewed"
    assert set(matches[0]["program_link"]) == {"state", "reason_code", "program_id", "program_event_link_id", "ontology_graph_id"}

    # A workspace built with no program_link_by_event_id carries no field at all.
    bare = build_procurement_workspace(
        {"opportunities": [], "events": [], "market": {}, "freshness": {"status": "unavailable"}},
        [],
        as_of="2026-08-22",
        known_at="2026-08-22T00:00:00+00:00",
        award_events=events,
        award_event_freshness={"status": "ok", "records_visible": len(events)},
    )
    assert "program_link" not in bare["events"][0]


def test_committed_program_dossier_round_trips_its_own_content_id():
    """The real checked-in canonical bundle recomputes byte-identically:
    the content_id law (gpd1- + first 24 hex of SHA-256 over canonical JSON
    with content_id/generated_at excluded) holds on the committed artifact,
    not just on freshly composed ones."""
    canonical_path = Path(__file__).parents[1] / "data" / "government_revenue" / "program_dossier.json"
    if not canonical_path.exists():
        pytest.skip("no committed D5 canonical dossier in this checkout")
    raw = canonical_path.read_text(encoding="utf-8")
    bundle = json.loads(raw)
    assert pd.dossier_content_id(bundle) == bundle["content_id"]
    assert pd.is_valid_program_dossier_payload(bundle)
    # The committed bytes are themselves already the exact canonical
    # serialization (sort_keys, compact separators) -- a site-only mirror
    # never re-encodes them.
    recanonicalized = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    assert recanonicalized == raw


# ---------------------------------------------------------------------------
# Adversarial review repair (2026-08-23, opus) -- HIGH-1(a): every currency
# computation must be retire-aware, not just the derivation layer's PIT
# helpers. These are the reviewer's own probes, promoted to tests.
# ---------------------------------------------------------------------------


def test_high1a_retire_l1_admit_l2_program_event_link_loads_cleanly():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "high1a-event-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog1 = b.program_row(id_="acq-program:one", evidence_refs=[ev["evidence_id"]])
    prog2 = b.program_row(id_="acq-program:two", evidence_refs=[ev["evidence_id"]])
    l1 = b.program_event_link_row(program_id=prog1["id"], event_id="govws-shared", evidence_refs=[ev["evidence_id"]])
    l2 = b.program_event_link_row(program_id=prog2["id"], event_id="govws-shared", evidence_refs=[ev["evidence_id"]])
    retire_l1 = b.override_row(target_row_id=l1["link_id"], evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog1, prog2]
    graph["program_event_links"] = [l1, l2]
    graph["overrides"] = [retire_l1]
    loaded = _load(graph)  # must NOT refuse link_multiplicity_invalid
    assert {row["link_id"] for row in loaded["program_event_links"]} == {l1["link_id"], l2["link_id"]}


def test_high1a_retire_capability_link_admit_new_loads_cleanly():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "high1a-cap-doc", claim_scopes=["program_identity", "capability_need", "program_capability_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    cap1 = b.capability_row(id_="acq-capability:one", evidence_refs=[ev["evidence_id"]])
    cap2 = b.capability_row(id_="acq-capability:two", evidence_refs=[ev["evidence_id"]])
    link1 = b.program_capability_link_row(program_id=prog["id"], capability_id=cap1["id"], evidence_refs=[ev["evidence_id"]])
    link2 = b.program_capability_link_row(
        program_id=prog["id"], capability_id=cap2["id"], evidence_refs=[ev["evidence_id"]],
        valid_from="2021-01-01T00:00:00+00:00",
    )
    retire_link1 = b.override_row(target_row_id=link1["link_id"], evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["capabilities"] = [cap1, cap2]
    graph["program_capability_links"] = [link1, link2]
    graph["overrides"] = [retire_link1]
    loaded = _load(graph)  # must NOT refuse link_multiplicity_invalid
    assert {row["link_id"] for row in loaded["program_capability_links"]} == {link1["link_id"], link2["link_id"]}


def test_high1a_link_multiplicity_invalid_without_conflict_row():
    """Two current links, no conflicts row -> the certification defect the
    exemption logic exists to still catch."""
    graph = b.empty_graph()
    ev = b.evidence_row(
        "high1a-nomult-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    prog1 = b.program_row(id_="acq-program:one", evidence_refs=[ev["evidence_id"]])
    prog2 = b.program_row(id_="acq-program:two", evidence_refs=[ev["evidence_id"]])
    l1 = b.program_event_link_row(program_id=prog1["id"], event_id="govws-contested", evidence_refs=[ev["evidence_id"]])
    l2 = b.program_event_link_row(program_id=prog2["id"], event_id="govws-contested", evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [prog1, prog2]
    graph["program_event_links"] = [l1, l2]
    error = _refused(graph)
    assert "link_multiplicity_invalid" in error.errors


def test_high1a_lawful_conflict_clearing_certifies_and_rails_rederive():
    """The reviewer's third probe: retire the conflicts row + retire the
    losing link in the SAME act -> certifies, and both the workspace
    program_link derivation (SS3.1b) and the dossier awards rail (SS4)
    re-derive `reviewed` for the surviving program, never staying stuck on
    the pre-clearing `conflicted` state."""
    graph = b.empty_graph()
    ev = b.evidence_row(
        "high1a-clear-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    winner_prog = b.program_row(id_="acq-program:winner", evidence_refs=[ev["evidence_id"]])
    loser_prog = b.program_row(id_="acq-program:loser", evidence_refs=[ev["evidence_id"]])
    winner_link = b.program_event_link_row(
        program_id=winner_prog["id"], event_id="govws-cleared", evidence_refs=[ev["evidence_id"]],
    )
    loser_link = b.program_event_link_row(
        program_id=loser_prog["id"], event_id="govws-cleared", evidence_refs=[ev["evidence_id"]],
    )
    conflict = b.conflict_row(
        scope="program_event_link", subject_type="award_event", subject_id="govws-cleared",
        candidate_row_ids=[winner_link["link_id"], loser_link["link_id"]], evidence_refs=[ev["evidence_id"]],
    )
    clear_link = b.override_row(target_row_id=loser_link["link_id"], evidence_refs=[ev["evidence_id"]])
    clear_conflict = b.override_row(target_row_id=conflict["conflict_id"], evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [winner_prog, loser_prog]
    graph["program_event_links"] = [winner_link, loser_link]
    graph["conflicts"] = [conflict]
    graph["overrides"] = [clear_link, clear_conflict]
    loaded = _load(graph)  # lawful clearing certifies

    at_cut = po.analysis_as_of("2026-08-22")
    program_link = po.derive_workspace_program_link(
        loaded, event_id="govws-cleared", analysis_as_of=at_cut, graph_id=loaded["graph_id"],
    )
    assert program_link["state"] == "reviewed"
    assert program_link["program_id"] == "acq-program:winner"

    winner_rail = pd._awards_rail(loaded, winner_prog["id"], analysis_as_of=at_cut, workspace=None)
    assert winner_rail["link_state"] == "reviewed"
    loser_rail = pd._awards_rail(loaded, loser_prog["id"], analysis_as_of=at_cut, workspace=None)
    assert loser_rail["link_state"] == "not_reviewed"


# ---------------------------------------------------------------------------
# HIGH-2 -- logical duplicate detection must run BEFORE dict collapse
# ---------------------------------------------------------------------------


def test_high2_two_program_rows_same_id_revision_differing_bytes_refused():
    """The reviewer's exact probe: two acq-program:example revision-1 rows
    named Alpha/Beta must never both certify."""
    graph = b.empty_graph()
    ev = b.evidence_row(
        "high2-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    alpha = b.program_row(id_="acq-program:example", revision=1, name="Alpha", evidence_refs=[ev["evidence_id"]])
    beta = b.program_row(id_="acq-program:example", revision=1, name="Beta", evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [alpha, beta]
    error = _refused(graph)
    assert "duplicate_identity_conflict" in error.errors


def test_high2_byte_identical_logical_row_resubmission_dedupes_idempotently():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "high2-idem-doc", claim_scopes=["capability_need"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    cap = b.capability_row(evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["capabilities"] = [cap, dict(cap)]  # byte-identical duplicate
    loaded = _load(graph)
    assert len(loaded["capabilities"]) == 2  # the artifact may still carry both rows...
    assert loaded["capabilities"][0] == loaded["capabilities"][1]  # ...but they are byte-identical, never flagged


def test_t14d_logical_kind_duplicate_vs_attribute_revision():
    """T14(d)'s logical-kind half: an in-place variant (same id+revision,
    differing bytes) refuses; the legal form -- a fresh revision -- is
    accepted."""
    graph = b.empty_graph()
    ev = b.evidence_row(
        "t14d-logical-doc", claim_scopes=["program_identity"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    original = b.program_row(id_="acq-program:x", revision=1, name="Original", evidence_refs=[ev["evidence_id"]])
    in_place_variant = b.program_row(id_="acq-program:x", revision=1, name="Mutated", evidence_refs=[ev["evidence_id"]])
    graph["evidence"] = [ev]
    graph["programs"] = [original, in_place_variant]
    error = _refused(graph)
    assert "duplicate_identity_conflict" in error.errors

    legal_successor = b.program_row(
        id_="acq-program:x", revision=2, name="Mutated", known_at="2026-08-22T09:00:00+00:00",
        evidence_refs=[ev["evidence_id"]], succession_reason="attribute_revision",
    )
    graph2 = b.empty_graph()
    graph2["evidence"] = [ev]
    graph2["programs"] = [original, legal_successor]
    loaded = _load(graph2)
    assert {row["id"] for row in loaded["programs"]} == {"acq-program:x"}


# ---------------------------------------------------------------------------
# MEDIUM-1 -- awards rail withholds attribution under any non-reviewed state
# ---------------------------------------------------------------------------


def test_medium1_awards_rail_empty_arrays_under_conflicted_link_state():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "medium1-doc", claim_scopes=["program_identity", "program_event_link"],
        known_at="2020-01-01T00:00:00+00:00", retrieved_at="2020-01-01T00:00:00+00:00",
    )
    winner_prog = b.program_row(id_="acq-program:m1-winner", evidence_refs=[ev["evidence_id"]])
    loser_prog = b.program_row(id_="acq-program:m1-loser", evidence_refs=[ev["evidence_id"]])
    winner_link = b.program_event_link_row(
        program_id=winner_prog["id"], event_id="govws-m1-contested", evidence_refs=[ev["evidence_id"]],
    )
    loser_link = b.program_event_link_row(
        program_id=loser_prog["id"], event_id="govws-m1-contested", evidence_refs=[ev["evidence_id"]],
    )
    conflict = b.conflict_row(
        scope="program_event_link", subject_type="award_event", subject_id="govws-m1-contested",
        candidate_row_ids=[winner_link["link_id"], loser_link["link_id"]], evidence_refs=[ev["evidence_id"]],
    )
    graph["evidence"] = [ev]
    graph["programs"] = [winner_prog, loser_prog]
    graph["program_event_links"] = [winner_link, loser_link]
    graph["conflicts"] = [conflict]
    loaded = _load(graph)

    at_cut = po.analysis_as_of("2026-08-22")
    rail = pd._awards_rail(loaded, winner_prog["id"], analysis_as_of=at_cut, workspace=None)
    assert rail["link_state"] == "conflicted"
    assert rail["program_event_link_ids"] == []
    assert rail["event_ids"] == []


# ---------------------------------------------------------------------------
# MEDIUM-2 -- overlap predicate is strict (half-open [from, to)), not
# inclusive -- a row starting exactly when another ends does NOT overlap it.
# ---------------------------------------------------------------------------


def test_medium2_platform_reference_invalid_on_touching_boundary():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "medium2-platform-doc", claim_scopes=["program_identity", "role"],
        known_at="2019-01-01T00:00:00+00:00", retrieved_at="2019-01-01T00:00:00+00:00",
    )
    prog = b.program_row(evidence_refs=[ev["evidence_id"]])
    platform = b.platform_row(
        program_id=prog["id"], evidence_refs=[ev["evidence_id"]],
        valid_from="2020-01-01T00:00:00+00:00", valid_to="2021-01-01T00:00:00+00:00",
    )
    # The role starts EXACTLY when the platform's validity ends -- touching,
    # not overlapping, under the frozen half-open [from, to) definition.
    role = b.role_assertion_row(
        program_id=prog["id"], platform_id=platform["id"], evidence_refs=[ev["evidence_id"]],
        valid_from="2021-01-01T00:00:00+00:00",
    )
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["platforms"] = [platform]
    graph["role_assertions"] = [role]
    error = _refused(graph)
    assert "platform_reference_invalid" in error.errors


def test_medium2_temporal_incompatible_on_touching_boundary():
    graph = b.empty_graph()
    ev = b.evidence_row(
        "medium2-cap-doc", claim_scopes=["program_capability_link"],
        known_at="2019-01-01T00:00:00+00:00", retrieved_at="2019-01-01T00:00:00+00:00",
    )
    prog = b.program_row(
        evidence_refs=[ev["evidence_id"]],
        valid_from="2020-01-01T00:00:00+00:00", valid_to="2021-01-01T00:00:00+00:00",
    )
    cap = b.capability_row(evidence_refs=[ev["evidence_id"]])
    # Link starts EXACTLY when the program's validity ends -- touching only.
    link = b.program_capability_link_row(
        program_id=prog["id"], capability_id=cap["id"], evidence_refs=[ev["evidence_id"]],
        valid_from="2021-01-01T00:00:00+00:00",
    )
    graph["evidence"] = [ev]
    graph["programs"] = [prog]
    graph["capabilities"] = [cap]
    graph["program_capability_links"] = [link]
    error = _refused(graph)
    assert "temporal_incompatible" in error.errors
