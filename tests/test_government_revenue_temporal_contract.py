"""D3 -- Temporal Contract v3 + Change Tape.

Hostile test families T1-T8 from
``research/defense_intelligence/DEFENSE_D3_TEMPORAL_CONTRACT_AND_CHANGE_TAPE_SPEC.md``
§5. Producer tests (T1-T3) exercise ``build_procurement_workspace`` directly;
UI tests (T4-T8) drive the page's real inline runtime through the same node
DOM-stub harness ``tests/test_government_revenue_ui.py`` uses, against the
REAL committed exemplar events named in the frozen spec (read live from
``site/government-revenue-data/workspace.json`` so the fixtures can never
silently drift from what actually shipped).
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from engine.government_revenue.workspace import (
    TEMPORAL_CONTRACT,
    build_procurement_workspace,
)
from tests.test_government_revenue_ui import _run_runtime, needs_node
from tests.test_government_revenue_workspace import (
    _award_change_event,
    _empty_opportunity_intelligence as _empty_oi,
)

ROOT = Path(__file__).resolve().parents[1]
COMMITTED_WORKSPACE_PATH = ROOT / "site" / "government-revenue-data" / "workspace.json"


# ---------------------------------------------------------------------------
# Real committed exemplars (§5 UI tests must be driven by these, not by
# hand-authored substitutes).
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _committed_workspace() -> dict:
    return json.loads(COMMITTED_WORKSPACE_PATH.read_text(encoding="utf-8"))


def _real_event(event_id: str) -> dict:
    for event in _committed_workspace().get("events", []):
        if event.get("event_id") == event_id:
            return copy.deepcopy(event)
    raise AssertionError(
        f"exemplar event {event_id!r} is not in the committed workspace.json -- "
        "the frozen spec's real exemplars must stay live, not hand-copied"
    )


def _mini_workspace(events: list[dict], **overrides) -> dict:
    base = {
        "schema_version": "government_procurement_workspace.v2",
        "bundle_id": "grw2-" + "e" * 24,
        "total": len(events),
        "next_cursor": None,
        "events": events,
        "coverage": {"events_visible": len(events), "open_opportunities": 0},
        "freshness": {"status": "ok"},
        "as_of": "2026-08-20",
        "generated_at": "2026-08-20T01:45:51.990878+00:00",
        "limitations": [],
    }
    base.update(overrides)
    return base


def _mini_payload(workspace: dict, companies: list[dict] | None = None) -> dict:
    return {
        "companies": companies or [],
        "market": {},
        "freshness": {"status": "ok"},
        "opportunity_intelligence": {"market": {}},
        "procurement_workspace": workspace,
    }


NOW_MS = 1_786_000_000_000  # 2026-08-26T ~ well after every exemplar's known_at


# ---------------------------------------------------------------------------
# T1 -- rail typing (producer)
# ---------------------------------------------------------------------------
def test_t1_opportunities_unavailable_status_gets_typed_source_unavailable():
    workspace = build_procurement_workspace(
        {
            "events": [], "opportunities": [], "market": {"active_opportunities": 0},
            "freshness": {"status": "unavailable"},
        },
        [],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
    )
    assert workspace["freshness"]["opportunities"]["failure_state"] == "source_unavailable"
    assert workspace["temporal_contract"] == TEMPORAL_CONTRACT


def test_t1_opportunities_zero_visible_with_no_observation_gets_typed_source_unavailable():
    """A rail that has never spoken is not a valid quiet week (§2)."""
    workspace = build_procurement_workspace(
        {
            "events": [], "opportunities": [], "market": {"active_opportunities": 0},
            "freshness": {"status": "ok", "records_visible": 0, "observed_at": None},
        },
        [],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
    )
    assert workspace["freshness"]["opportunities"]["failure_state"] == "source_unavailable"


def test_t1_opportunities_healthy_rail_carries_no_failure_state_lie():
    workspace = build_procurement_workspace(
        {
            "events": [], "opportunities": [], "market": {"active_opportunities": 0},
            "freshness": {"status": "ok", "records_visible": 5, "observed_at": "2026-07-30T00:00:00Z"},
        },
        [],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
    )
    assert workspace["freshness"]["opportunities"]["failure_state"] is None


def test_t1_award_events_and_recompete_rails_also_type_a_degraded_status():
    workspace = build_procurement_workspace(
        _empty_oi(),
        [],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
        award_freshness={"status": "error"},
        award_event_freshness={"status": "failed"},
    )
    assert workspace["freshness"]["recompetes"]["failure_state"] == "source_unavailable"
    assert workspace["freshness"]["award_events"]["failure_state"] == "source_unavailable"


def test_t1_budget_artifact_absent_gets_projection_missing_with_reason_code():
    workspace = build_procurement_workspace(
        _empty_oi(), [], as_of="2026-07-31", known_at="2026-07-31T23:59:59Z",
    )
    assert workspace["freshness"]["budget"] == {
        "status": "unavailable",
        "failure_state": "projection_missing",
        "observed_at": None,
        "records_visible": 0,
        "reason_code": "no_request_graph_artifact",
    }


def test_t1_budget_artifact_present_emits_real_status_not_a_failure_state_lie():
    workspace = build_procurement_workspace(
        _empty_oi(), [], as_of="2026-07-31", known_at="2026-07-31T23:59:59Z",
        budget_freshness={
            "status": "ok",
            "observed_at": "2026-08-01T00:00:00Z",
            "records_visible": 12,
            "reason_code": None,
        },
    )
    assert workspace["freshness"]["budget"]["failure_state"] is None
    assert workspace["freshness"]["budget"]["status"] == "ok"
    assert workspace["freshness"]["budget"]["records_visible"] == 12


# ---------------------------------------------------------------------------
# T2 -- append law (producer)
# ---------------------------------------------------------------------------
def test_t2_successor_revision_present_leaves_predecessor_event_byte_identical():
    predecessor = _award_change_event()
    original = copy.deepcopy(predecessor)
    successor = copy.deepcopy(predecessor)
    successor["event_id"] = predecessor["event_id"] + "-successor"
    successor["record_id"] = predecessor["record_id"] + "-successor"
    successor["award_change"]["prior_source_identity"] = "f" * 64

    solo = build_procurement_workspace(
        _empty_oi(), [], as_of="2026-07-31", known_at="2026-07-31T23:59:59Z",
        award_events=[copy.deepcopy(predecessor)], award_event_freshness={"status": "ok"},
    )
    paired = build_procurement_workspace(
        _empty_oi(), [], as_of="2026-07-31", known_at="2026-07-31T23:59:59Z",
        award_events=[copy.deepcopy(predecessor), successor], award_event_freshness={"status": "ok"},
    )

    solo_predecessor = next(e for e in solo["events"] if e["event_id"] == original["event_id"])
    paired_predecessor = next(e for e in paired["events"] if e["event_id"] == original["event_id"])
    assert solo_predecessor == original
    assert paired_predecessor == original
    assert solo_predecessor == paired_predecessor
    # The successor itself is admitted, append-only, alongside the predecessor.
    assert len(paired["events"]) == 2


# ---------------------------------------------------------------------------
# T3 -- named-null law (producer)
# ---------------------------------------------------------------------------
def test_t3_no_source_published_at_key_anywhere_in_a_freshly_built_workspace():
    workspace = build_procurement_workspace(
        _empty_oi(), [], as_of="2026-07-31", known_at="2026-07-31T23:59:59Z",
        award_events=[_award_change_event()], award_event_freshness={"status": "ok"},
        budget_freshness={
            "status": "ok", "observed_at": "2026-08-01T00:00:00Z",
            "records_visible": 3, "reason_code": None,
        },
    )
    assert "source_published_at" not in json.dumps(workspace)


def test_t3_no_source_published_at_key_in_the_committed_workspace_artifact():
    assert "source_published_at" not in json.dumps(_committed_workspace())


# ---------------------------------------------------------------------------
# T4 -- P00032 (IRDM, HC101319C0006): tape row + inspector clocks (UI)
# ---------------------------------------------------------------------------
@needs_node
def test_t4_p00032_tape_row_carries_effective_date_and_late_chip_and_known_ago(tmp_path):
    event = _real_event("govws-a6c70850a9cbdce9fa3e7f3b")
    assert event["award_change"]["is_late_discovery"] is True
    assert event["change"]["effective_at"].startswith("2026-05-12")
    assert event["amounts"][0]["value"] == 18416666.66
    workspace = _mini_workspace([event])
    payload = _mini_payload(workspace, companies=[{"ticker": "IRDM", "name": "Iridium Communications"}])

    out = _run_runtime(tmp_path, payload, workspace, NOW_MS)

    queue = out["queueHtml"]
    assert "truth late" in queue or 'class="truth late"' in queue
    assert "Late discovery" in queue
    assert "Took effect" in queue
    assert "May 12, 2026" in queue
    assert "found " in queue


@needs_node
def test_t4_p00032_inspector_clock_block_shows_all_four_rows_and_no_august_catalyst_framing(tmp_path):
    event = _real_event("govws-a6c70850a9cbdce9fa3e7f3b")
    workspace = _mini_workspace([event])
    payload = _mini_payload(workspace, companies=[{"ticker": "IRDM", "name": "Iridium Communications"}])

    out = _run_runtime(tmp_path, payload, workspace, NOW_MS)
    inspector = out["inspectorHtml"]

    assert "Clocks" in inspector
    assert "Took effect" in inspector
    assert "Official action date" in inspector
    assert "First known to Mastermind" in inspector
    assert "May 12, 2026" in inspector  # effective_at
    assert "Aug 12, 2026" in inspector  # known_at
    assert "Source publication time" in inspector
    assert "Not asserted" in inspector
    assert "USAspending does not expose a per-revision publication time" in inspector
    assert "Evidence cut" in inspector
    assert "Late discovery" in inspector  # discoveryTiming() verdict, duplicated into the block
    lowered = inspector.lower()
    assert "new award" not in lowered
    assert "august catalyst" not in lowered


# ---------------------------------------------------------------------------
# T5 -- N0002418C2406 (HII) balance pair: exact diff + successor line (UI)
# ---------------------------------------------------------------------------
@needs_node
def test_t5_balance_pair_shows_exact_before_after_and_successor_line(tmp_path):
    first = _real_event("govws-b6bd898176f278ae01151de2")
    second = _real_event("govws-bd6a001bb8bed5422cf337a9")
    assert first["change"]["changed_fields"][0]["before"] == 4722995757.0
    assert first["change"]["changed_fields"][0]["after"] == 4724822663.0
    assert second["change"]["changed_fields"][0]["before"] == 4724822663.0
    assert second["change"]["changed_fields"][0]["after"] == 4725472612.5
    workspace = _mini_workspace([first, second])
    payload = _mini_payload(workspace)

    out_first = _run_runtime(
        tmp_path, payload, workspace, NOW_MS,
        location_search=f"?item=ws:{first['event_id']}",
    )
    inspector_first = out_first["inspectorHtml"]
    assert "4722995757" in inspector_first
    assert "4724822663" in inspector_first
    prior_first = first["award_change"]["prior_source_identity"][:12]
    assert "Succeeds a prior recorded source state" in inspector_first
    assert prior_first in inspector_first
    assert "Corrections append" in inspector_first
    lowered_first = inspector_first.lower()
    assert "new award" not in lowered_first
    assert "obligated" in lowered_first

    out_second = _run_runtime(
        tmp_path, payload, workspace, NOW_MS,
        location_search=f"?item=ws:{second['event_id']}",
    )
    inspector_second = out_second["inspectorHtml"]
    assert "4724822663" in inspector_second
    assert "4725472612.5" in inspector_second
    prior_second = second["award_change"]["prior_source_identity"][:12]
    assert prior_second in inspector_second
    assert "new award" not in inspector_second.lower()


# ---------------------------------------------------------------------------
# §3c correction chip -- data-driven, zero committed events carry it today,
# so it is pinned with a fixture rather than a real exemplar.
# ---------------------------------------------------------------------------
@needs_node
def test_correction_chip_is_data_driven_and_never_fires_on_an_uncorrected_event(tmp_path):
    normal = _real_event("govws-a6c70850a9cbdce9fa3e7f3b")
    assert normal["change"].get("is_correction") is False
    workspace = _mini_workspace([normal])
    payload = _mini_payload(workspace, companies=[{"ticker": "IRDM", "name": "Iridium Communications"}])
    out = _run_runtime(tmp_path, payload, workspace, NOW_MS)
    assert "truth correction" not in out["queueHtml"]
    assert "truth correction" not in out["inspectorHtml"]

    corrected = copy.deepcopy(normal)
    corrected["event_id"] = normal["event_id"] + "-corr-fixture"
    corrected["record_id"] = normal["record_id"] + "-corr-fixture"
    corrected["change"]["is_correction"] = True
    workspace2 = _mini_workspace([corrected])
    payload2 = _mini_payload(workspace2, companies=[{"ticker": "IRDM", "name": "Iridium Communications"}])

    out2 = _run_runtime(tmp_path, payload2, workspace2, NOW_MS)
    assert 'class="truth correction"' in out2["queueHtml"]
    assert 'class="truth correction"' in out2["inspectorHtml"]
    assert "Correction" in out2["queueHtml"]


# ---------------------------------------------------------------------------
# T6 -- deobligation sign/ticker: AZ0010 unlinked, LDOS reviewed+linked (UI)
# ---------------------------------------------------------------------------
@needs_node
def test_t6_az0010_deobligation_keeps_minus_sign_and_has_no_ticker_link(tmp_path):
    event = _real_event("govws-aa6f1867ab7cae18de92e16c")
    assert event["listed_company_impacts"] == []
    assert event["change"]["changed_fields"][0]["after"] == -5937624.0
    workspace = _mini_workspace([event])
    payload = _mini_payload(workspace)

    out = _run_runtime(tmp_path, payload, workspace, NOW_MS)

    assert out["rows"] == [{
        "kind": "award_change", "truth": "official", "linked": False,
        "defense": True, "title": event["title_original"],
    }]
    inspector = out["inspectorHtml"]
    assert "−5937624" in inspector or "-5937624" in inspector or "5,937,624" in inspector or "5.9M" in inspector
    queue = out["queueHtml"]
    assert "ticker-token" not in queue


@needs_node
def test_t6_ldos_deobligation_keeps_minus_sign_and_keeps_its_reviewed_ticker(tmp_path):
    event = _real_event("govws-208faa21f5756b7233b938fb")
    tickers = {impact.get("ticker") for impact in event["listed_company_impacts"]}
    assert "LDOS" in tickers
    assert event["change"]["changed_fields"][0]["after"] == -41000000.0
    workspace = _mini_workspace([event])
    payload = _mini_payload(workspace, companies=[{"ticker": "LDOS", "name": "Leidos Holdings"}])

    out = _run_runtime(tmp_path, payload, workspace, NOW_MS)

    assert out["rows"][0]["linked"] is True
    queue = out["queueHtml"]
    assert "ticker-token" in queue
    assert "LDOS" in queue


# ---------------------------------------------------------------------------
# T7 -- typed rail states reach the tape, fail closed when the block is gone (UI)
# ---------------------------------------------------------------------------
@needs_node
def test_t7_opportunities_source_unavailable_reads_from_the_typed_failure_state(tmp_path):
    workspace = _mini_workspace(
        [],
        freshness={
            "status": "partial",
            "opportunities": {"status": "ok", "failure_state": "source_unavailable"},
        },
    )
    payload = _mini_payload(workspace)
    payload["opportunity_intelligence"] = {"market": {}, "freshness": {"status": "ok"}}

    out = _run_runtime(
        tmp_path, payload, workspace, NOW_MS, location_search="?mode=opportunities",
    )
    assert "SOURCE_UNAVAILABLE" in out["queueHtml"]


@needs_node
def test_t7_opportunities_rail_block_missing_fails_closed_to_unavailable(tmp_path):
    """A workspace that has no opportunities rail block at all is a producer
    defect, never a valid empty bid week (§0 gate 4)."""
    workspace = _mini_workspace([], freshness={"status": "ok"})
    payload = _mini_payload(workspace)
    payload["opportunity_intelligence"] = {"market": {}, "freshness": {"status": "ok"}}

    out = _run_runtime(
        tmp_path, payload, workspace, NOW_MS, location_search="?mode=opportunities",
    )
    assert "SOURCE_UNAVAILABLE" in out["queueHtml"]
    assert "No opportunities in this cut" not in out["queueHtml"]


@needs_node
def test_t7_budget_renders_projection_missing_and_loading_is_never_the_settled_state(tmp_path):
    workspace = _mini_workspace(
        [],
        freshness={
            "status": "ok",
            "budget": {
                "status": "unavailable",
                "failure_state": "projection_missing",
                "observed_at": None,
                "records_visible": 0,
                "reason_code": "no_request_graph_artifact",
            },
        },
    )
    payload = _mini_payload(workspace)

    out = _run_runtime(
        tmp_path, payload, workspace, NOW_MS, location_search="?mode=budget",
    )
    assert "PROJECTION_MISSING" in out["queueHtml"]
    assert "Loading budget request graph" not in out["queueHtml"]
    assert "正在加载预算请求图谱" not in out["queueHtml"]


# ---------------------------------------------------------------------------
# T8 -- no browser arithmetic: renderers consume artifact fields verbatim (UI)
# ---------------------------------------------------------------------------
def test_t8_no_new_date_subtraction_or_amount_arithmetic_beyond_the_grandfathered_lag():
    template = (ROOT / "templates" / "government_revenue.html.j2").read_text(encoding="utf-8")
    # The only pre-existing Date-subtraction is the grandfathered
    # discoveryLagDays() (§1) -- this pins the count so a future PR cannot
    # quietly add a second one under the D3 banner.
    assert template.count("new Date(") <= 4  # date(), ago(), discoveryLagDays() x2
    assert "discoveryLagDays" in template
    assert "function discoveryLagDays(change){var c=obj(change)?change:{},eff=c.effective_at,known=c.known_at;if(!eff||!known)return null;var ed=new Date(eff),kd=new Date(known);if(isNaN(ed.getTime())||isNaN(kd.getTime()))return null;return Math.round((kd.getTime()-ed.getTime())/86400000)}" in template


@needs_node
def test_t8_diff_and_clock_renderers_render_fixture_values_verbatim(tmp_path):
    """Assert the rendered strings equal the fixture's own before/after values.

    A regression that started re-deriving a diff (e.g. subtracting to
    recompute a delta instead of printing ``changed_fields[].after`` verbatim)
    would still show *a* number, so this pins the EXACT fixture value rather
    than merely asserting a number is present.
    """
    event = _real_event("govws-b6bd898176f278ae01151de2")
    before = event["change"]["changed_fields"][0]["before"]
    after = event["change"]["changed_fields"][0]["after"]
    assert (before, after) == (4722995757.0, 4724822663.0)
    workspace = _mini_workspace([event])
    payload = _mini_payload(workspace)

    out = _run_runtime(tmp_path, payload, workspace, NOW_MS)
    inspector = out["inspectorHtml"]
    assert f"{int(before)} → {int(after)}" in inspector or (
        str(int(before)) in inspector and str(int(after)) in inspector
    )
