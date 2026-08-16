"""Executable BioCatalyst client hydration-state classification.

These tests run the shipped IIFE against a stub DOM and a scripted fetch table.
They exist to keep validator throws, parse failures, access errors, empty pages,
and 5xx outages from collapsing into the same generic unavailable painter.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"
JS = TEMPLATES / "biocatalyst.js"
HARNESS = Path(__file__).with_name("biocatalyst_hydration_harness.js")
HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

AS_OF = "2026-08-16T12:00:00Z"
AUTHORITY = {
    "classification": "source_fact",
    "decision_authority": False,
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "raise_authority",
    ],
}
CEILING_AUTHORITY = {
    "decision_authority": False,
    "maximum_authority": "A1_EXPLAIN",
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "raise_authority",
    ],
}


def _json(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _meta(**extra: object) -> dict:
    body = {
        "schema_version": "biocatalyst_api.v1",
        "as_of": AS_OF,
        "source": {"name": "ClinicalTrials.gov"},
        "health": {"state": "fresh"},
        "coverage": {"class": "current_only"},
        "authority": AUTHORITY,
    }
    body.update(extra)
    return body


def milestone_empty() -> dict:
    return _meta(
        milestones=[],
        pagination={"limit": 50, "total": 0, "next_cursor": None},
        query={
            "milestone_kind": "primary_completion",
            "window": "next_90d",
            "from_date": "",
            "to_date": "",
            "q": "",
            "phase": "",
            "status": "",
            "condition": "",
        },
        effective_window={
            "from_date": "2026-08-16",
            "to_date": "2026-11-14",
            "anchor_date": "2026-08-16",
        },
    )


def prospective_pre_baseline_empty() -> dict:
    return _meta(
        prospective_changes=[],
        pagination={"limit": 50, "total": 0, "next_cursor": None},
        query={
            "change_kind": "all",
            "window": "last_90d",
            "q": "",
            "phase": "",
            "status": "",
            "condition": "",
        },
        effective_window={
            "from_date": "2026-05-18",
            "to_date": "2026-08-16",
            "anchor_date": "2026-08-16",
            "anchor_at": AS_OF,
            "date_basis": "observation_at_or_before_utc",
        },
        prospective_coverage={
            "class": "prospective_current_only",
            "selection_basis": "current_trial_record",
            "coverage_state": "pre_baseline",
            "active_trials": 0,
            "pre_baseline_trials": 4,
            "unavailable_trials": 0,
            "coverage_started_at": AS_OF,
            "last_observed_at": AS_OF,
        },
    )


def screen_one_row() -> dict:
    observed = lambda value: {"state": "observed", "value": value}
    row = {
        "nct_id": "NCT00000001",
        "brief_title": observed("Alpha Study"),
        "official_title": observed("Official Alpha Study"),
        "overall_status": observed("RECRUITING"),
        "study_type": observed("INTERVENTIONAL"),
        "phases": observed("PHASE2"),
        "sponsor": observed("Acme"),
        "enrollment": observed("100"),
        "conditions": observed("Oncology"),
        "interventions": observed("Drug"),
        "primary_completion": {
            "state": "observed",
            "literal": "2026-12",
            "precision": "month",
            "interval": {"start": "2026-12-01", "end": "2026-12-31"},
        },
        "source": {
            "url": "https://clinicaltrials.gov/study/NCT00000001",
            "retrieved_at": AS_OF,
        },
    }
    return {
        "contract_id": "trial_screen_read_model.v1",
        "schema_version": "1.0.0",
        "as_of": AS_OF,
        "rows": [row],
        "row_count": 1,
        "sort_order": "primary_completion_interval_ascending_then_nct_id",
        "pagination": {
            "limit": 50,
            "offset": 0,
            "total": 1,
            "returned": 1,
            "next_cursor": None,
        },
        "coverage": {"class": "current_only", "matched": 1, "observed": 1},
        "source": {"name": "ClinicalTrials.gov"},
        "authority": CEILING_AUTHORITY,
        "query": {
            "filter_composition": "literal_and",
            "primary_completion_matching": "full_interval_containment",
            "sponsor": "",
            "intervention": "",
            "study_type": "",
            "phase": "",
            "status": "",
            "condition": "",
            "primary_completion_from": "",
            "primary_completion_to": "",
        },
    }


def _route(status: int, body: str, content_type: str = "application/json") -> dict:
    return {"status": status, "body": body, "contentType": content_type}


def _run(tmp_path: Path, scenario: dict, js_text: str | None = None) -> dict:
    js_path = tmp_path / "biocatalyst.js"
    js_path.write_text(js_text if js_text is not None else JS.read_text(encoding="utf-8"), encoding="utf-8")
    scene_path = tmp_path / "scenario.json"
    scene_path.write_text(json.dumps(scenario), encoding="utf-8")
    result = subprocess.run(
        ["node", str(HARNESS), str(scene_path), str(js_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return json.loads(result.stdout)


def _forbidden_machine_text(text: str) -> None:
    lowered = text.lower()
    for token in (
        "contractfailed",
        "schema_version",
        "biocatalyst_api.v1",
        "trial_screen_read_model",
        "syntaxerror",
        "typeerror",
        "stack",
        "invalid milestone list contract",
        "invalid trial screen contract",
    ):
        assert token not in lowered, text


@needs_node
def test_401_paints_locked_not_generic_unavailable(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(401, '{"detail":"auth"}')
            }
        },
    )["first"]
    assert out["workspaceState"] == "locked"
    assert out["decisionState"] == "locked"
    assert "Full access required" in out["status"]
    assert "Registry page unavailable" not in out["queue"]
    _forbidden_machine_text(out["queue"] + out["notice"] + out["status"])


@needs_node
def test_trial_screen_valid_nonzero_is_normal(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "search": "?mode=screen",
            "routes": {
                "/api/biocatalyst/v1/trials:screen": _route(200, _json(screen_one_row())),
                "/api/biocatalyst/v1/trials:screen/facets": _route(
                    503, '{"detail":"facets optional"}'
                ),
            },
        },
    )["first"]
    assert out["workspaceState"] == "ready"
    assert out["decisionState"] == "normal"
    assert "NCT00000001" in out["queue"]
    assert "Registry page unavailable" not in out["queue"]


@needs_node
def test_milestones_valid_zero_is_empty_not_outage(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {"routes": {"/api/biocatalyst/v1/trials/milestones": _route(200, _json(milestone_empty()))}},
    )["first"]
    assert out["workspaceState"] == "empty"
    assert out["decisionState"] == "empty"
    assert "No recorded dates" in out["queue"]
    assert "Registry page unavailable" not in out["queue"]
    assert "source_outage" not in (out["workspaceState"], out["decisionState"])


@needs_node
def test_first_seen_pre_baseline_zero_is_valid_empty(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "search": "?mode=prospective",
            "routes": {
                "/api/biocatalyst/v1/trials/prospective-changes": _route(
                    200, _json(prospective_pre_baseline_empty())
                )
            },
        },
    )["first"]
    assert out["workspaceState"] == "empty"
    assert out["decisionState"] == "empty"
    assert "baseline" in out["queue"].lower() or "No first-seen observations" in out["queue"]
    assert "Registry page unavailable" not in out["queue"]
    assert out["workspaceState"] != "source_outage"


@needs_node
def test_503_paints_source_outage(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    503, '{"detail":"trial intelligence temporarily unavailable"}'
                )
            }
        },
    )["first"]
    assert out["workspaceState"] == "source_outage"
    assert out["decisionState"] == "source_outage"
    assert "Temporarily unavailable" in out["queue"]
    assert "Registry page unavailable" not in out["queue"]
    assert "ClinicalTrials.gov" not in out["notice"]
    _forbidden_machine_text(out["queue"] + out["notice"] + out["status"])


@needs_node
def test_valid_json_wrong_contract_is_integrity_block(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    200, _json({"schema_version": "not-the-contract", "milestones": []})
                )
            }
        },
    )["first"]
    assert out["workspaceState"] == "integrity_block"
    assert out["decisionState"] == "integrity_block"
    assert "Results withheld" in out["queue"]
    assert "Registry page unavailable" not in out["queue"]
    assert "ClinicalTrials.gov" not in out["notice"]
    _forbidden_machine_text(out["queue"] + out["notice"] + out["status"] + out["why"])


@needs_node
def test_malformed_200_json_is_integrity_block(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(200, "{not json", "application/json")
            }
        },
    )["first"]
    assert out["workspaceState"] == "integrity_block"
    assert "Results withheld" in out["queue"]
    assert "Registry page unavailable" not in out["queue"]
    _forbidden_machine_text(out["queue"] + out["notice"])


@needs_node
def test_validator_throw_cannot_reach_generic_unavailable_painter(tmp_path: Path) -> None:
    js = JS.read_text(encoding="utf-8")
    load_body = js[js.index("function loadMilestones(") : js.index("function applyFilters()")]
    assert "handleUnavailable(error, { append: append });" not in load_body
    assert "paintUnavailableWorkspace()" not in load_body
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    200, _json({"ok": True, "rows": "this is not a milestone envelope"})
                )
            }
        },
    )["first"]
    assert out["workspaceState"] == "integrity_block"
    assert "Registry page unavailable" not in out["queue"]
    assert "Registry page unavailable" not in out["status"]


@needs_node
def test_switching_from_failed_mode_to_healthy_mode_clears_failure(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(503, '{"detail":"down"}')
            },
            "clickMode": "screen",
            "secondRoutes": {
                "/api/biocatalyst/v1/trials:screen": _route(200, _json(screen_one_row())),
                "/api/biocatalyst/v1/trials:screen/facets": _route(503, "{}"),
            },
        },
    )
    assert out["first"]["workspaceState"] == "source_outage"
    assert out["second"]["workspaceState"] == "ready"
    assert out["second"]["decisionState"] == "normal"
    assert "Temporarily unavailable" not in out["second"]["queue"]
    assert "NCT00000001" in out["second"]["queue"]


@needs_node
def test_same_mode_refresh_from_integrity_to_503_is_source_outage(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    200, _json({"schema_version": "not-the-contract", "milestones": []})
                )
            },
            "clickRefresh": True,
            "secondRoutes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    503, '{"detail":"trial intelligence temporarily unavailable"}'
                )
            },
        },
    )
    first, second = out["first"], out["second"]
    assert first["workspaceState"] == "integrity_block"
    assert "Results withheld" in first["queue"]
    assert second["workspaceState"] == "source_outage"
    assert second["decisionState"] == "source_outage"
    assert "Temporarily unavailable" in second["queue"]
    assert "Results withheld" not in second["queue"]
    assert "received records failed an integrity check" not in (second["queue"] + second["notice"] + second["why"]).lower()
    assert "Integrity check did not pass" not in second["status"] + second["statusDetail"] + second["queue"]


@needs_node
def test_same_mode_refresh_from_503_to_wrong_contract_is_integrity_block(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    503, '{"detail":"trial intelligence temporarily unavailable"}'
                )
            },
            "clickRefresh": True,
            "secondRoutes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    200, _json({"schema_version": "not-the-contract", "milestones": []})
                )
            },
        },
    )
    first, second = out["first"], out["second"]
    assert first["workspaceState"] == "source_outage"
    assert "Temporarily unavailable" in first["queue"]
    assert second["workspaceState"] == "integrity_block"
    assert second["decisionState"] == "integrity_block"
    assert "Results withheld" in second["queue"]
    assert "Temporarily unavailable" not in second["queue"]
    assert "the trial service is not answering" not in (second["queue"] + second["notice"] + second["why"]).lower()


@needs_node
def test_html_content_type_on_valid_json_is_integrity_block(tmp_path: Path) -> None:
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    200, _json(milestone_empty()), "text/html"
                )
            }
        },
    )["first"]
    assert out["workspaceState"] == "integrity_block"
    assert out["decisionState"] == "integrity_block"
    assert "Results withheld" in out["queue"]
    assert "Temporarily unavailable" not in out["queue"]
    _forbidden_machine_text(out["queue"] + out["notice"] + out["status"] + out["why"])


@needs_node
def test_post_validation_render_exception_is_not_source_or_integrity(tmp_path: Path) -> None:
    needle = (
        "ui.workspace.dataset.state = state.restarted ? 'generation-restarted' : "
        "(state.rows.length ? 'ready' : 'empty'); updateMetadata(payload); "
        "setSubtitle(payload); renderQueue();"
    )
    hostile = (
        "ui.workspace.dataset.state = state.restarted ? 'generation-restarted' : "
        "(state.rows.length ? 'ready' : 'empty'); throw new Error('hostile render'); "
        "updateMetadata(payload); setSubtitle(payload); renderQueue();"
    )
    source = JS.read_text(encoding="utf-8")
    mutated = source.replace(needle, hostile, 1)
    assert mutated != source
    out = _run(
        tmp_path,
        {"routes": {"/api/biocatalyst/v1/trials/milestones": _route(200, _json(milestone_empty()))}},
        js_text=mutated,
    )["first"]
    copy = (out["queue"] + out["notice"] + out["status"] + out["statusDetail"] + out["why"]).lower()
    assert out["workspaceState"] not in ("source_outage", "integrity_block")
    assert out["decisionState"] not in ("source_outage", "integrity_block")
    assert "the trial service is not answering" not in copy
    assert "received records failed an integrity check" not in copy
    assert "results withheld" not in copy
    assert "hostile render" not in copy
    assert "typeerror" not in copy
    assert out["workspaceState"] == "withheld"
    assert "This page could not be shown" in out["queue"]
    _forbidden_machine_text(out["queue"] + out["notice"] + out["status"] + out["why"])


@needs_node
def test_mutation_routing_validator_through_generic_unavailable_fails_regression(
    tmp_path: Path,
) -> None:
    """If a later edit sends validator failure back through handleUnavailable, fail."""

    mutated = JS.read_text(encoding="utf-8").replace(
        "handleHydrationFailure(error, { append: append });",
        "handleUnavailable(error, { append: append });",
        1,
    )
    assert mutated != JS.read_text(encoding="utf-8")
    out = _run(
        tmp_path,
        {
            "routes": {
                "/api/biocatalyst/v1/trials/milestones": _route(
                    200, _json({"schema_version": "not-the-contract"})
                )
            }
        },
        js_text=mutated,
    )["first"]
    with pytest.raises(AssertionError):
        assert out["workspaceState"] == "integrity_block"
        assert "Registry page unavailable" not in out["queue"]
    assert out["workspaceState"] == "unavailable"
    assert "Registry page unavailable" in out["queue"]


def test_template_and_site_js_remain_byte_equivalent() -> None:
    assert JS.read_bytes() == (SITE / "biocatalyst.js").read_bytes()
    assert "function handleHydrationFailure(error, options)" in JS.read_text(encoding="utf-8")
    assert "function withAuth(headers)" in JS.read_text(encoding="utf-8")
    # Silent-auth fallback is out of scope for this PR.
    assert "}).catch(function () { return headers; });" in JS.read_text(encoding="utf-8")
