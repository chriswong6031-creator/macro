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
from scripts import build_baskets, build_government_revenue


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
        "schema_version": "1.0.0",
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


def test_builder_refuses_fixture_only_dod_bundle_activation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    templates = tmp_path / "templates"
    templates.mkdir()
    templates.joinpath("government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    _write_dod_budget_source_bundle(tmp_path)
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: _payload())

    canonical = tmp_path / "data" / "government_revenue" / "budget_program_graph.json"
    public = tmp_path / "site" / "government-revenue-data" / "budget-program.json"
    with pytest.raises(ValueError, match="publication is hard-disabled"):
        build_government_revenue.build(tmp_path)
    assert not canonical.exists()
    assert not public.exists()

    (tmp_path / "data" / "government_revenue" / "dod_budget_projection_state.json").unlink()
    with pytest.raises(ValueError, match="DoD budget source bundle is partial"):
        build_government_revenue.build(tmp_path)


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
