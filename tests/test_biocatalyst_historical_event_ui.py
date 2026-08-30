from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
HARNESS = Path(__file__).with_name("biocatalyst_hydration_harness.js")
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")


def _render(lang: str = "en") -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    html = env.get_template("biocatalyst.html.j2").render(
        generated_utc="runtime-api",
        active_section="research",
        active_page="biocatalyst",
        lang=lang,
    )
    return html


def _event() -> dict:
    return {
        "contract_id": "biocatalyst_historical_event_record.v1",
        "schema_version": "1.0.0",
        "event_id": "bpcjv_event_" + "a" * 24,
        "source": {"provider": "BioPharmCatalyst", "source_id": "biopharmcatalyst_jv_snapshot", "license_class": "licensed_finite_snapshot", "family": "historical_fda", "source_ordinal": 1, "capture_observed_at": "2026-08-17T07:55:47Z", "source_published_at": None, "source_published_at_state": "unknown"},
        "company": {"ticker_evidence": "ABC", "name_evidence": "Alpha Therapeutics", "resolution_state": "unresolved", "security_id": None, "issuer_id": None, "resolution_basis": "none", "issuer_relationship_state": "unavailable"},
        "event": {"date": "2024-01-01", "date_precision": "day", "family": "regulatory", "stage": "Approved", "description": "Approved for the recorded indication.", "source_available_at": None, "observed_at": "2026-08-17T07:55:47Z"},
        "asset": {"kind": "drug", "label": "Drug A", "indication": "Cancer"},
        "historical_market": {"price_at_event": "$10", "price_movement": "+5%"},
        "normalization": {"state": "deterministic", "repair": "missing_row_index_unshifted"},
        "unsafe_fields": ["capture_only_overlays_unavailable"],
        "authority": {"classification": "licensed_historical_context", "decision_authority": False, "allowed_uses": ["display", "context", "explain"], "forbidden_uses": ["originate_signal", "rank_security", "select_security", "size_position", "gate_decision", "execute_trade", "raise_authority"]},
    }


def _payload(*, rows: list[dict] | None = None, state: str = "partial") -> dict:
    rows = [_event()] if rows is None else rows
    return {
        "schema_version": "1.0.0",
        "state": state,
        "as_of": "2026-08-24T20:00:00Z",
        "capture_observed_at": "2026-08-17T07:55:47Z",
        "source": {"provider": "BioPharmCatalyst", "source_id": "biopharmcatalyst_jv_snapshot", "license_class": "licensed_finite_snapshot", "availability": "last_admitted_finite_snapshot"},
        "coverage": {"state": "partial", "source_rows": 17205, "normalized_rows": 16396, "identity_resolved": 4068, "identity_unresolved": 12328, "duplicates_collapsed": 409, "families": {"historical_fda": 15295, "device_history": 661, "device_pipeline_history": 440}, "family_source_rows": {"historical_fda": 15700, "device_history": 666, "device_pipeline_history": 839}},
        "authority": {"classification": "licensed_historical_context", "decision_authority": False, "allowed_uses": ["display", "context", "explain"], "forbidden_uses": ["originate_signal", "rank_security", "select_security", "size_position", "gate_decision", "execute_trade", "raise_authority"]},
        "query": {"q": None, "family": "all", "stage": None, "asset": None, "from_date": None, "to_date": None},
        "pagination": {"limit": 50, "total": len(rows), "next_cursor": None},
        "historical_events": rows,
    }


def _run(tmp_path: Path, route: dict, *, lang: str = "en") -> dict:
    scene = {
        "lang": lang,
        "routes": {
            "/api/biocatalyst/v1/catalyst-radar": {
                "status": 200,
                "body": json.dumps({
                    "schema_version": "biocatalyst_api.v1", "as_of": "2026-08-24T20:00:00Z", "source": {"name": "ClinicalTrials.gov"}, "health": {"state": "fresh"}, "coverage": {"class": "current_only", "radar": {"trials_in_cohort": 0, "trials_with_events": 0, "events_total": 0, "events_in_horizon": 0, "events_occurred": 0, "events_current": 0, "events_beyond_horizon": 0, "unusable_date_events": 0, "absent_date_events": 0, "trials_missing_identity": 0, "kinds": ["primary_completion", "completion"], "horizon_days": 365, "anchor_date": "2026-08-24"}}, "authority": {"classification": "source_fact", "decision_authority": False, "allowed_uses": ["display", "context", "explain"], "forbidden_uses": ["originate_signal", "rank_security", "select_security", "size_position", "gate_decision", "execute_trade", "raise_authority"]}, "query": {"horizon": "next_365d", "milestone_kind": "all", "q": "", "phase": "", "status": "", "condition": ""}, "effective_horizon": {"horizon": "next_365d", "horizon_days": 365, "anchor_date": "2026-08-24"}, "pagination": {"limit": 50, "total": 0, "next_cursor": None}, "catalyst_radar": []
                }),
                "contentType": "application/json",
            },
            "/api/biocatalyst/v1/historical-events": route,
        },
    }
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps(scene), encoding="utf-8")
    result = subprocess.run(
        ["node", str(HARNESS), str(scene_path), str(TEMPLATES / "biocatalyst.js")],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)["first"]


def test_shell_contains_one_bilingual_history_workspace() -> None:
    page = _render()
    for element_id in (
        "bci-history", "bci-history-search", "bci-history-family",
        "bci-history-from", "bci-history-to", "bci-history-stage",
        "bci-history-asset",
    ):
        assert page.count(f'id="{element_id}"') == 1
    assert "Historical Event History" in page
    assert "历史事件记录" in page
    assert '<option value="all"><span' not in page
    assert 'data-label-zh="全部类别"' in page


@needs_node
def test_real_history_payload_renders_row_and_typed_detail(tmp_path: Path) -> None:
    out = _run(tmp_path, {"status": 200, "body": json.dumps(_payload()), "contentType": "application/json"})
    assert out["historyState"] == "partial"
    assert "Alpha Therapeutics" in out["historyRows"]
    assert "Drug A" in out["historyRows"]
    assert "Identity unresolved" in out["historyRows"]
    assert "Deterministically repaired" in out["historyRows"]
    assert any("/api/biocatalyst/v1/historical-events" in call for call in out["fetchCalls"])


@needs_node
@pytest.mark.parametrize(
    ("status", "body", "expected_state", "expected_text"),
    [
        (200, _payload(rows=[], state="empty"), "empty", "No historical events match"),
        (401, {"detail": "auth"}, "locked", "Full access required"),
        (503, {"detail": "down"}, "unavailable", "Historical event history unavailable"),
    ],
)
def test_history_typed_empty_locked_and_unavailable_states(tmp_path: Path, status: int, body: dict, expected_state: str, expected_text: str) -> None:
    out = _run(tmp_path, {"status": status, "body": json.dumps(body), "contentType": "application/json"})
    assert out["historyState"] == expected_state
    assert expected_text in out["historyRows"] + out["historyStatus"]


@needs_node
def test_history_chinese_row_and_state_are_localized(tmp_path: Path) -> None:
    out = _run(tmp_path, {"status": 200, "body": json.dumps(_payload()), "contentType": "application/json"}, lang="zh")
    assert "身份未解析" in out["historyRows"]
    assert "已确定性修复" in out["historyRows"]
