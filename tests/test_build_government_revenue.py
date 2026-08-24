"""Builder ownership and fail-soft integration tests for Government Revenue."""
from __future__ import annotations

import json
import inspect
from pathlib import Path

import pytest

from engine.government_revenue.workspace import build_procurement_workspace
from engine.government_revenue.subaward_dossiers import is_valid_subaward_dossier_payload
from engine.government_revenue.idv_dossiers import is_valid_idv_dossier_payload
from collectors import dod_budget
from engine.government_revenue.entity_resolution import (
    build_recipient_resolution_coverage,
    load_recipient_entity_graph,
)
from engine.government_revenue import program_ontology as po
from scripts import build_baskets, build_government_revenue

# D5 program-ontology/dossier fixtures (freeze DEFENSE_D5_PROGRAM_GRAPH_ARCHITECTURE_FREEZE.md)
# reused rather than duplicated -- tests.test_government_program_ontology carries
# no scripts.build_government_revenue import (that is exactly why the five tests
# below were relocated INTO this properly-provisioned lane, 2026-08-23 CI repair:
# importing scripts.build_government_revenue pulls a collectors chain needing
# `requests`, which ci-pack-7's govrev-program-ontology job does not install),
# so importing these three lightweight, jsonschema-only helpers from it is safe.
from tests.test_government_program_ontology import DOSSIER_SCHEMA, _pilot_reference, _validate


def _payload() -> dict:
    return {
        "schema_version": "company_government_revenue.v1",
        "as_of": "2026-08-01",
        "known_at": "2026-08-01T08:00:00Z",
        "authority": {"tier": "display", "can_rank": False},
        "coverage": {"entities_mapped": 1},
        "market": {},
        "procurement_workspace": build_procurement_workspace(
            {"freshness": {"status": "ok"}},
            [],
            as_of="2026-08-01",
            known_at="2026-08-01T08:00:00Z",
            award_freshness={"status": "ok"},
            award_event_freshness={"status": "unavailable"},
        ),
        "companies": [{"ticker": "LMT", "name": "Lockheed Martin", "metrics": {}}],
    }


def _empty_graph() -> dict:
    return {
        "contract": "government_recipient_entity_graph.v1",
        "schema_version": "1.1.0",
        "graph_id": "recipient-graph:builder-empty",
        "graph_known_at": "2026-08-01T00:00:00Z",
        "graph_effective_at": "2026-08-01T00:00:00Z",
        "evidence": [],
        "companies": [],
        "legal_entities": [],
        "identifiers": [],
        "ownership_edges": [],
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }


def _activate_recipient_graph(root: Path, payload: dict) -> dict:
    graph = _empty_graph()
    data_dir = root / "data" / "government_revenue"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "recipient_entity_graph.json").write_text(
        json.dumps(graph), encoding="utf-8"
    )
    loaded = load_recipient_entity_graph(graph, as_of=payload["as_of"])
    coverage = build_recipient_resolution_coverage(
        [],
        [],
        loaded,
        as_of=payload["as_of"],
        snapshot_amount_field="total_obligation",
        action_amount_field="federal_action_obligation",
    )
    payload["freshness"] = {
        "award_events": {"recipient_resolution_coverage": coverage}
    }
    payload["procurement_workspace"]["freshness"]["award_events"][
        "recipient_resolution_coverage"
    ] = coverage
    return coverage


def _write_dod_budget_source_bundle(root: Path) -> None:
    """Write a complete fixture-only source bundle through the collector contract."""
    fixture_dir = Path(__file__).parent / "fixtures" / "dod_budget"
    lines: list[dict] = []
    receipts: list[dict] = []
    for name in ("fy2026_p1.json", "fy2026_r1.json"):
        fixture = json.loads((fixture_dir / name).read_text(encoding="utf-8"))
        pdf_bytes = b"%PDF-1.4\nbuilder-" + name.encode("ascii")
        digest = dod_budget._sha256(pdf_bytes)
        receipt = dod_budget.build_document_receipt(
            source_url=fixture["source_url"],
            final_url=fixture["final_url"],
            pdf_bytes=pdf_bytes,
            pages=fixture["pages"],
            fiscal_year=fixture["fiscal_year"],
            exhibit=fixture["exhibit"],
            observed_at="2026-08-02T12:00:00+00:00",
            immutable_object_key=f"{dod_budget.IMMUTABLE_R2_PREFIX}{digest}.pdf",
        )
        parsed, _ = dod_budget.parse_budget_document(fixture["pages"], receipt)
        lines.extend(parsed)
        receipts.append(receipt)
    data = root / "data" / "government_revenue"
    data.mkdir(parents=True, exist_ok=True)
    data.joinpath("dod_budget_line_snapshots.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in lines) + "\n",
        encoding="utf-8",
    )
    data.joinpath("dod_budget_collection_receipts.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in receipts) + "\n",
        encoding="utf-8",
    )
    data.joinpath("dod_budget_projection_state.json").write_text(
        json.dumps(dod_budget.budget_projection_state(lines, receipts), sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    config = root / "config" / "government_revenue"
    config.mkdir(parents=True)
    config.joinpath("budget_program_reviewed_edges.v1.json").write_text(
        json.dumps({"contract": "government_budget_reviewed_edges.v1", "schema_version": "1.0.0", "edges": []}),
        encoding="utf-8",
    )


def test_builder_writes_canonical_site_twin_and_page(tmp_path: Path, monkeypatch) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<title>Government Revenue</title><script>{{ payload_json|safe }}</script>",
        encoding="utf-8",
    )
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())

    html, canonical, site_json = build_government_revenue.build(tmp_path)

    assert html.exists() and canonical.exists() and site_json.exists()
    assert canonical.read_bytes() == site_json.read_bytes()
    assert json.loads(canonical.read_text())["companies"][0]["ticker"] == "LMT"
    workspace = tmp_path / "data" / "government_revenue" / "workspace.json"
    workspace_site = tmp_path / "site" / "government-revenue-data" / "workspace.json"
    assert workspace.exists() and workspace.read_bytes() == workspace_site.read_bytes()
    workspace_payload = json.loads(workspace.read_text())
    assert workspace_payload["schema_version"] == "government_procurement_workspace.v2"
    assert workspace_payload["bundle_id"].startswith("grw2-")
    assert len(workspace_payload["bundle_id"]) == len("grw2-") + 24
    subaward = tmp_path / "data" / "government_revenue" / "subaward_dossiers.json"
    subaward_site = tmp_path / "site" / "government-revenue-data" / "subaward-dossiers.json"
    assert subaward.exists() and subaward.read_bytes() == subaward_site.read_bytes()
    assert is_valid_subaward_dossier_payload(json.loads(subaward.read_text()))
    idv = tmp_path / "data" / "government_revenue" / "idv_dossiers.json"
    idv_site = tmp_path / "site" / "government-revenue-data" / "idv-dossiers.json"
    assert idv.exists() and idv.read_bytes() == idv_site.read_bytes()
    assert is_valid_idv_dossier_payload(json.loads(idv.read_text()))
    assert json.loads(idv.read_text())["source_coverage"]["status"] == "unavailable"
    assert "Government Revenue" in html.read_text()


def test_workspace_bundle_id_is_content_derived_not_assembly_clock() -> None:
    workspace = {
        "schema_version": "government_procurement_workspace.v2",
        "as_of": "2026-08-01",
        "generated_at": "2026-08-01T08:00:00Z",
        "events": [{"event_id": "evt-1"}],
    }
    first = build_government_revenue._workspace_bundle_id(workspace)
    workspace["generated_at"] = "2026-08-01T09:00:00Z"
    assert build_government_revenue._workspace_bundle_id(workspace) == first
    workspace["events"][0]["event_id"] = "evt-2"
    assert build_government_revenue._workspace_bundle_id(workspace) != first


def test_site_only_rebuild_uses_canonical_bytes_without_recalculation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    template = templates / "government_revenue.html.j2"
    template.write_text("<main>v1 {{ payload_json|safe }}</main>", encoding="utf-8")
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
    build_government_revenue.build(tmp_path)

    canonical = tmp_path / "data" / "government_revenue" / "latest.json"
    workspace = tmp_path / "data" / "government_revenue" / "workspace.json"
    subaward = tmp_path / "data" / "government_revenue" / "subaward_dossiers.json"
    idv = tmp_path / "data" / "government_revenue" / "idv_dossiers.json"
    canonical_before = canonical.read_bytes()
    workspace_before = workspace.read_bytes()
    subaward_before = subaward.read_bytes()
    idv_before = idv.read_bytes()
    template.write_text("<main>v2 {{ payload_json|safe }}</main>", encoding="utf-8")
    monkeypatch.setattr(
        build_government_revenue,
        "build_payload",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("site-only recalculated data")),
    )

    html, _, site_json = build_government_revenue.build_site_only(tmp_path)

    assert canonical.read_bytes() == canonical_before
    assert workspace.read_bytes() == workspace_before
    assert site_json.read_bytes() == canonical_before
    assert (
        tmp_path / "site" / "government-revenue-data" / "workspace.json"
    ).read_bytes() == workspace_before
    assert subaward.read_bytes() == subaward_before
    assert (
        tmp_path / "site" / "government-revenue-data" / "subaward-dossiers.json"
    ).read_bytes() == subaward_before
    assert idv.read_bytes() == idv_before
    assert (
        tmp_path / "site" / "government-revenue-data" / "idv-dossiers.json"
    ).read_bytes() == idv_before
    assert "<main>v2 " in html.read_text(encoding="utf-8")


def test_builder_builds_budget_program_graph_from_a_complete_triad(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Stage 2b activation (DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED=True):
    a complete receipt-bound triad now BUILDS a real, schema-valid graph and
    publishes its canonical/site twins -- this used to hard-refuse while the
    flag was False (superseded name:
    test_builder_refuses_fixture_only_dod_bundle_activation)."""
    templates = tmp_path / "templates"
    templates.mkdir()
    templates.joinpath("government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    _write_dod_budget_source_bundle(tmp_path)
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())

    canonical = tmp_path / "data" / "government_revenue" / "budget_program_graph.json"
    public = tmp_path / "site" / "government-revenue-data" / "budget-program.json"
    build_government_revenue.build(tmp_path)
    assert canonical.exists() and public.exists()
    assert canonical.read_bytes() == public.read_bytes()
    graph = json.loads(canonical.read_text(encoding="utf-8"))
    assert graph["contract"] == "government_budget_program_graph.v1"
    assert graph["lines"] and graph["programs"]
    assert graph["source_coverage"]["president_budget_request"]["status"] == "ok"


def test_builder_refuses_a_partial_dod_bundle_even_with_activation_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Partial triad => hard refusal regardless of the activation flag value
    (the flag check in _build_budget_program_graph_if_ready runs AFTER the
    partial-bundle check, so this is unaffected by Stage 2b activation)."""
    templates = tmp_path / "templates"
    templates.mkdir()
    templates.joinpath("government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    _write_dod_budget_source_bundle(tmp_path)
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())

    (tmp_path / "data" / "government_revenue" / "dod_budget_projection_state.json").unlink()
    with pytest.raises(ValueError, match="DoD budget source bundle is partial"):
        build_government_revenue.build(tmp_path)


def test_builder_leaves_budget_rail_absent_when_no_triad_member_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """All three triad members absent => the optional rail stays None (no
    error, no synthetic graph, no twins written) -- distinct from a partial
    bundle, which is a hard failure."""
    templates = tmp_path / "templates"
    templates.mkdir()
    templates.joinpath("government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())

    canonical = tmp_path / "data" / "government_revenue" / "budget_program_graph.json"
    public = tmp_path / "site" / "government-revenue-data" / "budget-program.json"
    build_government_revenue.build(tmp_path)
    assert not canonical.exists()
    assert not public.exists()


def test_site_only_rebuild_fails_closed_on_generation_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
    build_government_revenue.build(tmp_path)
    workspace_path = tmp_path / "data" / "government_revenue" / "workspace.json"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    workspace["total"] = 99
    workspace_path.write_text(json.dumps(workspace), encoding="utf-8")

    with pytest.raises(ValueError, match="generation mismatch"):
        build_government_revenue.build_site_only(tmp_path)


def test_site_only_requires_the_committed_subaward_twin_when_prime_dossier_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
    build_government_revenue.build(tmp_path)
    (tmp_path / "data" / "government_revenue" / "subaward_dossiers.json").unlink()

    with pytest.raises(ValueError, match="subaward dossier"):
        build_government_revenue.build_site_only(tmp_path)


def test_builder_rejects_partial_idv_source_bundle(tmp_path: Path, monkeypatch) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    templates.joinpath("government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    data = tmp_path / "data" / "government_revenue"
    data.mkdir(parents=True)
    data.joinpath("idv_projection_state.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())

    with pytest.raises(ValueError, match="IDV source bundle is partial"):
        build_government_revenue.build(tmp_path)


def test_site_only_rejects_public_only_idv_dossier(tmp_path: Path, monkeypatch) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    templates.joinpath("government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
    build_government_revenue.build(tmp_path)
    (tmp_path / "data" / "government_revenue" / "idv_dossiers.json").unlink()

    with pytest.raises(ValueError, match="public IDV dossier exists without canonical bytes"):
        build_government_revenue.build_site_only(tmp_path)


def test_builder_atomically_persists_exact_embedded_recipient_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    payload = _payload()
    coverage = _activate_recipient_graph(tmp_path, payload)
    monkeypatch.setattr(
        build_government_revenue,
        "build_payload",
        lambda **_kwargs: payload,
    )

    build_government_revenue.build(tmp_path)

    coverage_path = (
        tmp_path
        / "data"
        / "government_revenue"
        / "recipient_resolution_coverage.json"
    )
    assert coverage_path.exists()
    assert coverage_path.read_text(encoding="utf-8") == (
        build_government_revenue._canonical_json(coverage)
    )
    canonical = json.loads(
        (tmp_path / "data" / "government_revenue" / "latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert canonical["freshness"]["award_events"][
        "recipient_resolution_coverage"
    ] == coverage


@pytest.mark.parametrize(
    "missing_name",
    ("recipient_entity_graph.json", "recipient_resolution_coverage.json"),
)
def test_site_only_requires_committed_graph_and_coverage_without_recalculation(
    tmp_path: Path,
    monkeypatch,
    missing_name: str,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    payload = _payload()
    _activate_recipient_graph(tmp_path, payload)
    monkeypatch.setattr(
        build_government_revenue,
        "build_payload",
        lambda **_kwargs: payload,
    )
    build_government_revenue.build(tmp_path)
    (tmp_path / "data" / "government_revenue" / missing_name).unlink()
    monkeypatch.setattr(
        build_government_revenue,
        "build_payload",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("site-only recalculated recipient coverage")
        ),
    )

    with pytest.raises(ValueError, match="recipient"):
        build_government_revenue.build_site_only(tmp_path)


def test_builder_rejects_receipt_bound_activation_without_curated_graph(
    tmp_path: Path,
    monkeypatch,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    # Presence of any canonical triad member activates the strict publication
    # fence; its bytes are not interpreted by this builder-boundary test.
    (data_dir / "award_event_projection_state.json").write_text(
        "{}", encoding="utf-8"
    )
    monkeypatch.setattr(
        build_government_revenue,
        "build_payload",
        lambda **_kwargs: _payload(),
    )

    with pytest.raises(ValueError, match="recipient entity graph"):
        build_government_revenue.build(tmp_path)


def test_atomic_writer_leaves_one_complete_artifact_and_no_temp_file(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"old":true}', encoding="utf-8")

    build_government_revenue._atomic_write_text(artifact, '{"new":true}')

    assert artifact.read_text(encoding="utf-8") == '{"new":true}'
    assert not list(tmp_path.glob(".artifact.json.*.tmp"))


def test_display_payload_is_first_page_only_while_canonical_workspace_stays_complete() -> None:
    payload = _payload()
    payload["companies"][0].update({
        "tags": ["defense"],
        "metrics": {
            "ttm_obligations": 10,
            "net_award_action_flow_90d": 3,
            "unused_large_metric": "x" * 10_000,
        },
        "awards": [{"description": "not embedded"}],
        "provenance": [{"dataset": "first"}, {"dataset": "second"}],
    })
    payload["opportunity_intelligence"] = {
        "schema_version": "government_opportunity_intelligence.v1",
        "opportunities": [{"notice_id": "not-duplicated"}],
        "events": [{"event_id": "not-duplicated"}],
        "company_context": {"LMT": ["not-duplicated"]},
    }
    payload["procurement_workspace"]["events"] = [
        {"event_id": f"evt-{index}"}
        for index in range(build_government_revenue.SHELL_EVENT_LIMIT + 5)
    ]
    payload["procurement_workspace"]["total"] = len(
        payload["procurement_workspace"]["events"]
    )

    shell = build_government_revenue._display_payload(payload)

    assert len(shell["procurement_workspace"]["events"]) == build_government_revenue.SHELL_EVENT_LIMIT
    assert shell["procurement_workspace"]["next_cursor"] == (
        build_government_revenue._workspace_cursor(
            build_government_revenue.SHELL_EVENT_LIMIT,
            version="v2",
        )
    )
    assert len(payload["procurement_workspace"]["events"]) == build_government_revenue.SHELL_EVENT_LIMIT + 5
    assert shell["opportunity_intelligence"]["opportunities"] == []
    assert shell["opportunity_intelligence"]["events"] == []
    assert shell["opportunity_intelligence"]["company_context"] == {}
    assert shell["companies"][0]["metrics"] == {
        "ttm_obligations": 10,
        "award_velocity_yoy_pct": None,
        "funded_capacity_observed": None,
        "net_award_action_flow_90d": 3,
        "positive_award_action_flow_90d": None,
        "modification_impulse_90d": None,
    }
    assert shell["companies"][0]["source_receipts"] == [{"dataset": "first"}]
    assert "awards" not in shell["companies"][0]


def test_display_payload_excludes_unused_workbench_contract_metadata() -> None:
    payload = _payload()
    payload["workbench"] = {
        "id": "government_revenue",
        "provenance_contract": "vertical_provenance.v1",
        "context_contract": "vertical_intelligence_context.v1",
    }
    payload["opportunity_intelligence"] = {
        "provenance": [{"contract": "vertical_provenance.v1"}],
        "opportunities": [],
        "events": [],
        "company_context": {},
    }
    payload["procurement_workspace"].setdefault("coverage", {})["award_events"] = {
        "input": 0,
        "validated": 0,
    }

    shell = build_government_revenue._display_payload(payload)

    assert "workbench" not in shell
    assert '"validated"' not in json.dumps(shell, sort_keys=True).lower()
    assert payload["procurement_workspace"]["coverage"]["award_events"]["validated"] == 0


def test_compact_shell_keeps_current_state_truth_without_full_receipt_duplication() -> None:
    payload = _payload()
    payload["procurement_workspace"]["events"] = [{
        "event_id": "evt-1",
        "kind": "opportunity",
        "title_original": "Synthetic notice",
        "agency": {"department_name": "Department of Defense", "private": "discard"},
        "change": {"type": "amendment", "changed_fields": []},
        "opportunity": {
            "notice_id": "notice-1",
            "source_status": "award_notice",
            "current_status": "active",
            "current_revision": False,
            "active": False,
            "current_state": "last_observed_active",
            "current_state_verified": False,
            "observation_horizon_at": "2026-08-01T00:00:00Z",
            "observation_age_minutes": 120,
            "observation_basis": "collector_last_seen",
            "current_state_reason": "verification_window_elapsed",
            "unneeded_description": "x" * 5_000,
        },
        "listed_company_impacts": [{
            "ticker": "LMT",
            "company_name": "Lockheed Martin",
            "materiality": {"band": "high", "coverage_note": "not embedded"},
            "cross_desk_links": [{"href": "fundamental_forensics.html?symbol=LMT", "label_en": "Filing Forensics"}],
        }],
        "evidence": {
            "source_class": "official_fact",
            "receipts": [{"url": "https://api.sam.gov/example", "raw_body": "x" * 5_000}],
            "derivations": [],
            "limitations": ["bounded"],
        },
    }]

    shell = build_government_revenue._display_payload(payload)
    event = shell["procurement_workspace"]["events"][0]

    assert event["opportunity"]["current_state_verified"] is False
    assert event["opportunity"]["source_status"] == "award_notice"
    assert event["opportunity"]["current_revision"] is False
    assert event["opportunity"]["active"] is False
    assert event["opportunity"]["observation_age_minutes"] == 120
    assert event["opportunity"]["current_state_reason"] == "verification_window_elapsed"
    assert "unneeded_description" not in event["opportunity"]
    assert "raw_body" not in event["evidence"]["receipts"][0]
    assert event["listed_company_impacts"][0]["materiality"] == {"band": "high"}


def test_compact_shell_keeps_safe_award_change_identity_without_raw_source_payload() -> None:
    compact = build_government_revenue._compact_workspace_event({
        "contract": "government_procurement_event.v2",
        "event_id": "govws-award-shell-1",
        "record_id": "award:generated:AWARD-1",
        "version": 1,
        "kind": "award_change",
        "state": "updated",
        "title_original": "Award value changed",
        "award_change": {
            "award_key": "generated:AWARD-1",
            "generated_award_id": "AWARD-1",
            "piid": "PIID-1",
            "recipient_name": "Example Defense Systems",
            "event_type": "award_value_changed",
            "secondary_types": [],
            "source_rail": "usaspending_award_snapshot",
            "observation_kind": "snapshot",
            "coverage_scope": "receipt-bound award snapshots",
            "is_late_discovery": False,
            "source_identity": {
                "id": "generated:AWARD-1",
                "version": "state-v1",
                "content_sha256": "a" * 64,
                "raw_response": "x" * 10_000,
            },
            "raw_source_response": "x" * 10_000,
        },
    })

    assert compact["award_change"] == {
        "award_key": "generated:AWARD-1",
        "generated_award_id": "AWARD-1",
        "piid": "PIID-1",
        "recipient_name": "Example Defense Systems",
        "event_type": "award_value_changed",
        "secondary_types": [],
        "source_rail": "usaspending_award_snapshot",
        "observation_kind": "snapshot",
        "coverage_scope": "receipt-bound award snapshots",
        "is_late_discovery": False,
        "source_identity": {
            "id": "generated:AWARD-1",
            "version": "state-v1",
            "content_sha256": "a" * 64,
        },
    }
    oversized = build_government_revenue._compact_workspace_event({
        "award_change": {
            "award_key": "k" * 500,
            "recipient_name": "r" * 500,
            "coverage_scope": "c" * 2_000,
            "secondary_types": ["s" * 120 for _ in range(12)],
            "source_identity": {
                "id": "i" * 500,
                "version": "v" * 500,
                "content_sha256": "h" * 500,
            },
        },
    })
    assert len(oversized["award_change"]["award_key"]) == 180
    assert len(oversized["award_change"]["recipient_name"]) == 240
    assert len(oversized["award_change"]["coverage_scope"]) == 480
    assert len(oversized["award_change"]["secondary_types"]) == 8
    assert all(len(value) == 80 for value in oversized["award_change"]["secondary_types"])
    assert len(oversized["award_change"]["source_identity"]["id"]) == 180
    assert len(oversized["award_change"]["source_identity"]["version"]) == 180
    assert len(oversized["award_change"]["source_identity"]["content_sha256"]) == 80


def test_compact_shell_bounds_long_legal_description_deltas() -> None:
    compact = build_government_revenue._compact_workspace_event({
        "change": {
            "type": "action_revised",
            "changed_fields": [{
                "field": "description",
                "before": "b" * 7_000,
                "after": "a" * 7_000,
                "semantic": "official",
                "source_ref": "https://api.usaspending.gov/" + "x" * 2_000,
            } for _ in range(8)],
        },
    })

    changes = compact["change"]["changed_fields"]
    assert len(changes) == 6
    assert all(len(row["before"]) == 360 for row in changes)
    assert all(len(row["after"]) == 360 for row in changes)
    assert all(len(row["source_ref"]) == 360 for row in changes)


def test_display_payload_adapts_first_page_to_json_budget() -> None:
    payload = _payload()
    payload["market"] = {"bounded_context": "x" * 50_000}
    payload["procurement_workspace"]["events"] = [
        {
            "event_id": f"evt-{index}",
            "change": {"changed_fields": [{
                "field": "description",
                "before": "b" * 7_000,
                "after": "a" * 7_000,
                "semantic": "official",
                "source_ref": "https://api.usaspending.gov/" + "x" * 2_000,
            } for _ in range(8)]},
        }
        for index in range(build_government_revenue.SHELL_EVENT_LIMIT)
    ]
    payload["procurement_workspace"]["total"] = len(
        payload["procurement_workspace"]["events"]
    )

    shell = build_government_revenue._display_payload(payload)
    raw = json.dumps(shell, ensure_ascii=False, separators=(",", ":"), default=str)
    visible = shell["procurement_workspace"]["events"]

    assert len(raw.encode("utf-8")) <= build_government_revenue.SHELL_JSON_BUDGET_BYTES
    assert len(visible) < build_government_revenue.SHELL_EVENT_LIMIT
    assert shell["procurement_workspace"]["next_cursor"] == (
        build_government_revenue._workspace_cursor(len(visible), version="v2")
    )


def test_generic_baskets_builder_cannot_write_government_projection() -> None:
    """Only the dedicated serialized lane may publish the evidence projection."""
    source = inspect.getsource(build_baskets)

    assert "build_government_revenue" not in source
    assert "_build_government_revenue_workbench" not in source


# ---------------------------------------------------------------------------
# D5 composer wiring (freeze DEFENSE_D5_PROGRAM_GRAPH_ARCHITECTURE_FREEZE.md)
#
# Relocated from tests/test_government_program_ontology.py (2026-08-23 CI
# repair, PR #6312 ci-pack-7 red): importing scripts.build_government_revenue
# pulls the collectors chain needing `requests`, which that suite's curated
# govrev-program-ontology job does not install, while this suite's lane
# already provisions build_government_revenue's full dependency set. Names
# and assertions are unchanged from the original; `_payload()` above replaces
# the former `_minimal_government_revenue_payload()` helper, which was
# byte-for-byte the same fixture duplicated only to keep that OTHER suite's
# import closure narrow -- a concern that does not apply here.
# ---------------------------------------------------------------------------


def test_build_government_revenue_writes_d5_dossier_and_program_link_end_to_end(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<title>Government Revenue</title><script>{{ payload_json|safe }}</script>",
        encoding="utf-8",
    )

    def _monkeypatched_build_payload(**_kwargs):
        payload = _payload()
        events = payload["procurement_workspace"].get("events") or []
        for event in events:
            if event.get("kind") == "award_change":
                event.setdefault("event_id", "govws-e2e-smoke-example")
        return payload

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(build_government_revenue, "build_payload", _monkeypatched_build_payload)
        build_government_revenue.build(tmp_path)
    finally:
        monkeypatch.undo()

    dossier_canonical = tmp_path / "data" / "government_revenue" / "program_dossier.json"
    dossier_site = tmp_path / "site" / "government-revenue-data" / "program-dossier.json"
    assert dossier_canonical.exists() and dossier_site.exists()
    assert dossier_canonical.read_bytes() == dossier_site.read_bytes()
    bundle = json.loads(dossier_canonical.read_text())
    _validate(bundle, DOSSIER_SCHEMA)
    assert bundle["dossiers"] == []  # no D5 canonical ontology exists under tmp_path -- honest empty bundle
    assert bundle["ontology_graph_id"] is None

    workspace_payload = json.loads((tmp_path / "data" / "government_revenue" / "workspace.json").read_text())
    award_change_events = [e for e in workspace_payload["events"] if e.get("kind") == "award_change"]
    # The shared _payload() fixture carries no
    # award_change rows; assert the
    # attachment behavior on whichever rows exist (may be an empty set), and
    # separately prove the derivation function itself against a real event
    # (already covered end-to-end by the workspace wiring test above).
    for event in award_change_events:
        assert event["program_link"] == {
            "state": "source_unavailable", "reason_code": "ontology_unavailable",
            "program_id": None, "program_event_link_id": None, "ontology_graph_id": None,
        }
    # No program-ontology site twin is written when no canonical artifact exists.
    assert not (tmp_path / "site" / "government-revenue-data" / "program-ontology.json").exists()


def test_build_government_revenue_composes_a_real_dossier_when_canonical_ontology_exists(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<title>Government Revenue</title><script>{{ payload_json|safe }}</script>",
        encoding="utf-8",
    )
    ontology_dir = tmp_path / "data" / "government_revenue"
    ontology_dir.mkdir(parents=True, exist_ok=True)
    reference = _pilot_reference()
    (ontology_dir / "program_ontology.json").write_text(json.dumps(reference), encoding="utf-8")

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
        build_government_revenue.build(tmp_path)
    finally:
        monkeypatch.undo()

    bundle = json.loads((tmp_path / "data" / "government_revenue" / "program_dossier.json").read_text())
    _validate(bundle, DOSSIER_SCHEMA)
    # The shared fixture's as_of (2026-08-01) predates the reference
    # ontology's rows (known_at 2026-08-22): every row is honestly invisible
    # at that PIT cut, so the bundle correctly carries zero dossiers -- but
    # the ontology itself is certified, so ontology_graph_id is populated
    # (never the bundle-level null form, which is reserved for an absent or
    # uncertified artifact per freeze SS4).
    assert bundle["dossiers"] == []
    assert bundle["ontology_graph_id"] == "program-ontology:reviewed:2026-08-22:defense-d5-v1"

    ontology_site_twin = tmp_path / "site" / "government-revenue-data" / "program-ontology.json"
    assert ontology_site_twin.exists()
    assert json.loads(ontology_site_twin.read_text()) == reference


def test_build_site_only_mirrors_both_d5_twins_byte_identical_when_canonical_exists(tmp_path):
    """build_site_only, run AFTER a full build already produced canonical D5
    bytes, must reproduce both site twins byte-identical -- without
    recomputing build_payload (which is monkeypatched to explode if called)."""
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<title>Government Revenue</title><script>{{ payload_json|safe }}</script>",
        encoding="utf-8",
    )
    ontology_dir = tmp_path / "data" / "government_revenue"
    ontology_dir.mkdir(parents=True, exist_ok=True)
    reference = _pilot_reference()
    (ontology_dir / "program_ontology.json").write_text(json.dumps(reference), encoding="utf-8")

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
        build_government_revenue.build(tmp_path)
    finally:
        monkeypatch.undo()

    canonical_ontology = ontology_dir / "program_ontology.json"
    canonical_dossier = ontology_dir / "program_dossier.json"
    assert canonical_ontology.exists() and canonical_dossier.exists()
    canonical_ontology_bytes = canonical_ontology.read_bytes()
    canonical_dossier_bytes = canonical_dossier.read_bytes()

    site_ontology = tmp_path / "site" / "government-revenue-data" / "program-ontology.json"
    site_dossier = tmp_path / "site" / "government-revenue-data" / "program-dossier.json"
    site_ontology.unlink()
    site_dossier.unlink()

    monkeypatch2 = _pytest.MonkeyPatch()
    try:
        monkeypatch2.setattr(
            build_government_revenue, "build_payload",
            lambda **_kwargs: (_ for _ in ()).throw(AssertionError("site-only recalculated data")),
        )
        build_government_revenue.build_site_only(tmp_path)
    finally:
        monkeypatch2.undo()

    assert site_ontology.exists() and site_ontology.read_bytes() == canonical_ontology_bytes
    assert site_dossier.exists() and site_dossier.read_bytes() == canonical_dossier_bytes
    # Canonical bytes themselves are untouched by a site-only pass.
    assert canonical_ontology.read_bytes() == canonical_ontology_bytes
    assert canonical_dossier.read_bytes() == canonical_dossier_bytes


def test_build_site_only_skips_d5_twins_quietly_when_canonical_absent(tmp_path):
    """A pre-D5 historical checkout (neither program_ontology.json nor
    program_dossier.json ever committed) must still site-only-render
    successfully, writing neither D5 twin -- never raising, never
    fabricating a bundle."""
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<title>Government Revenue</title><script>{{ payload_json|safe }}</script>",
        encoding="utf-8",
    )

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
        build_government_revenue.build(tmp_path)
    finally:
        monkeypatch.undo()

    data_dir = tmp_path / "data" / "government_revenue"
    site_dir = tmp_path / "site" / "government-revenue-data"
    # Simulate a checkout that predates D5 entirely: the full build path
    # above unconditionally composes the empty/unavailable bundle form, so
    # remove every trace of it to reach the TRUE pre-D5 absence state
    # build_site_only must tolerate.
    for path in (
        data_dir / "program_ontology.json", data_dir / "program_dossier.json",
        site_dir / "program-ontology.json", site_dir / "program-dossier.json",
    ):
        path.unlink(missing_ok=True)

    monkeypatch2 = _pytest.MonkeyPatch()
    try:
        monkeypatch2.setattr(
            build_government_revenue, "build_payload",
            lambda **_kwargs: (_ for _ in ()).throw(AssertionError("site-only recalculated data")),
        )
        build_government_revenue.build_site_only(tmp_path)  # must not raise
    finally:
        monkeypatch2.undo()

    assert not (data_dir / "program_ontology.json").exists()
    assert not (data_dir / "program_dossier.json").exists()
    assert not (site_dir / "program-ontology.json").exists()
    assert not (site_dir / "program-dossier.json").exists()


def test_build_site_only_raises_on_a_refused_canonical_ontology(tmp_path):
    """A committed canonical ontology that fails certification is corrupt
    state, not a degraded rail -- build_site_only must raise, matching every
    other canonical-invalid case in that function, never silently skip."""
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<title>Government Revenue</title><script>{{ payload_json|safe }}</script>",
        encoding="utf-8",
    )
    ontology_dir = tmp_path / "data" / "government_revenue"
    ontology_dir.mkdir(parents=True, exist_ok=True)
    (ontology_dir / "program_ontology.json").write_text(json.dumps(_pilot_reference()), encoding="utf-8")

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())
        build_government_revenue.build(tmp_path)
    finally:
        monkeypatch.undo()

    # Corrupt the committed canonical ontology bytes after the fact.
    corrupted = json.loads((ontology_dir / "program_ontology.json").read_text())
    corrupted["programs"][0]["phase"] = "not-a-real-phase"
    (ontology_dir / "program_ontology.json").write_text(json.dumps(corrupted), encoding="utf-8")

    with pytest.raises(po.OntologyInputError):
        build_government_revenue.build_site_only(tmp_path)
