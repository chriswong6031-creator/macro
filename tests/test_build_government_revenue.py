"""Builder ownership and fail-soft integration tests for Government Revenue."""
from __future__ import annotations

import json
import inspect
from pathlib import Path

import pytest

from scripts import build_baskets, build_government_revenue


def _payload() -> dict:
    return {
        "schema_version": "company_government_revenue.v1",
        "as_of": "2026-08-01",
        "known_at": "2026-08-01T08:00:00Z",
        "authority": {"tier": "display", "can_rank": False},
        "coverage": {"entities_mapped": 1},
        "market": {},
        "procurement_workspace": {
            "schema_version": "government_procurement_workspace.v1",
            "events": [],
            "total": 0,
        },
        "companies": [{"ticker": "LMT", "name": "Lockheed Martin", "metrics": {}}],
    }


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
    assert workspace_payload["schema_version"] == "government_procurement_workspace.v1"
    assert workspace_payload["bundle_id"].startswith("grw1-")
    assert len(workspace_payload["bundle_id"]) == len("grw1-") + 24
    assert "Government Revenue" in html.read_text()


def test_workspace_bundle_id_is_content_derived_not_assembly_clock() -> None:
    workspace = {
        "schema_version": "government_procurement_workspace.v1",
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
    canonical_before = canonical.read_bytes()
    workspace_before = workspace.read_bytes()
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
    assert "<main>v2 " in html.read_text(encoding="utf-8")


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
    assert shell["procurement_workspace"]["next_cursor"] == str(
        build_government_revenue.SHELL_EVENT_LIMIT
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
    assert shell["companies"][0]["provenance"] == [{"dataset": "first"}]
    assert "awards" not in shell["companies"][0]


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


def test_generic_baskets_builder_cannot_write_government_projection() -> None:
    """Only the dedicated serialized lane may publish the evidence projection."""
    source = inspect.getsource(build_baskets)

    assert "build_government_revenue" not in source
    assert "_build_government_revenue_workbench" not in source
