"""The CA1A machine consumer, proven on fixed fixtures with EXACT expectations.

The report is the wave's real consumer: if these numbers can drift, the producers are
unmeasurable and the wave is an infrastructure-only patch — the thing the commission
explicitly prohibits (research/commercial_activation/CLAUDE_ORCHESTRATOR_HANDOFF_V1
_CA1A_EVENT_SPINE_20260903.md §15.22-24). So every assertion here is exact (counts,
ratios, the leak sentence's bytes), and the null-contract cases (missing denominator,
unknown identity) are pinned as NULLS, never zeros.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "activation_funnel_report", ROOT / "scripts" / "activation_funnel_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AFR = _load_module()

SINCE = datetime(2026, 9, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 9, 2, tzinfo=timezone.utc)


def _row(type_: str, sid: str, *, meta=None, ua="Mozilla/5.0", visitor="v-1",
         user=None, created="2026-09-01T12:00:00+00:00", client="2026-09-01T11:59:58+00:00"):
    return {"type": type_, "session_id": sid, "meta": meta, "ua": ua,
            "visitor_id": visitor, "user_id": user,
            "created_at": created, "client_ts": client}


def _full_session(sid: str, visitor: str = "v-1") -> list[dict]:
    return [
        _row("session_start", sid, visitor=visitor),
        _row("intelligence.viewed", sid, visitor=visitor,
             meta={"surface": "flow_velocity", "surface_group": "read",
                   "tier_seen": "anon", "rows_visible": 3}),
        _row("personal.act", sid, visitor=visitor,
             meta={"act": "watchlist_add", "surface": "watchlist"}),
        _row("watchlist.saved", sid, visitor=visitor,
             meta={"symbol_count": 3, "list_count": 1, "storage": "local"}),
    ]


def test_exact_stage_counts_and_ratios_on_a_fixed_fixture():
    rows = (
        _full_session("s-full")
        + [_row("session_start", "s-visit-only")]
        + [_row("session_start", "s-value-only"),
           _row("intelligence.viewed", "s-value-only",
                meta={"surface": "flow_velocity", "surface_group": "read",
                      "tier_seen": "anon", "rows_visible": 1})]
        + [_row("session_start", "s-act-no-save"),
           _row("intelligence.viewed", "s-act-no-save",
                meta={"surface": "flow_velocity", "surface_group": "read",
                      "tier_seen": "anon", "rows_visible": 2}),
           _row("personal.act", "s-act-no-save",
                meta={"act": "watchlist_add", "surface": "watchlist"})]
    )
    rep = AFR.build_report(rows, SINCE, UNTIL, set(), set())
    assert rep["stage_sessions"] == {
        "visit": 4, "intelligence_viewed": 3, "personal_act": 2, "watchlist_saved": 1,
    }
    assert rep["conversion"] == {
        "intelligence_viewed_over_visit": 0.75,
        "personal_act_over_intelligence_viewed": round(2 / 3, 4),
        "watchlist_saved_over_personal_act": 0.5,
    }
    assert rep["rows_admitted"] == len(rows)


def test_largest_leak_sentence_is_deterministic_and_exact():
    rows = (
        _full_session("s-1")
        + [_row("session_start", f"s-visit-{i}") for i in range(3)]
    )
    rep = AFR.build_report(rows, SINCE, UNTIL, set(), set())
    # visit=4 -> value=1 loses 3; every later transition loses 0.
    assert rep["largest_leak"] == (
        "Largest leak: visit -> intelligence_viewed: 4 -> 1 sessions "
        "(25.0% continue, 3 lost)."
    )


def test_missing_denominator_reports_null_not_zero():
    rep = AFR.build_report([], SINCE, UNTIL, set(), set())
    assert rep["stage_sessions"]["visit"] == 0
    for ratio in rep["conversion"].values():
        assert ratio is None, "a ratio with no denominator must be null, never 0"
    assert rep["largest_leak"] == "No leak measurable: no stage has a non-zero denominator."


def test_saved_below_three_symbols_does_not_count_as_saved_stage():
    rows = [_row("session_start", "s-2"),
            _row("watchlist.saved", "s-2",
                 meta={"symbol_count": 2, "list_count": 1, "storage": "local"})]
    rep = AFR.build_report(rows, SINCE, UNTIL, set(), set())
    assert rep["stage_sessions"]["watchlist_saved"] == 0


def test_bot_and_internal_exclusion_is_versioned_and_counted():
    rows = (
        _full_session("s-real")
        + [_row("session_start", "s-bot", ua="Mozilla/5.0 (compatible; Googlebot/2.1)")]
        + [_row("session_start", "s-internal", visitor="v-internal")]
        + [dict(r, user_id="11111111-1111-1111-1111-111111111111")
           for r in _full_session("s-staff", visitor="v-9")]
    )
    rep = AFR.build_report(
        rows, SINCE, UNTIL,
        internal_users={"11111111-1111-1111-1111-111111111111"},
        internal_visitors={"v-internal"},
    )
    assert rep["filter_version"] == "commercial_activation_filter.v1"
    assert rep["stage_sessions"]["visit"] == 1          # only s-real survives
    assert rep["rows_dropped"]["bot_ua"] == 1
    assert rep["rows_dropped"]["internal_visitor"] == 1
    assert rep["rows_dropped"]["internal_user"] == 4    # the whole staff session


def test_ingestion_window_is_enforced_and_reported():
    rows = (_full_session("s-in")
            + [_row("session_start", "s-late", created="2026-09-03T00:00:00+00:00")])
    rep = AFR.build_report(rows, SINCE, UNTIL, set(), set())
    assert rep["stage_sessions"]["visit"] == 1
    assert rep["rows_dropped"]["outside_window"] == 1
    assert rep["ingestion_cutoff"] == {
        "since": "2026-09-01T00:00:00+00:00", "until": "2026-09-02T00:00:00+00:00",
    }
    assert rep["occurrence_observed_max"] == "2026-09-01T11:59:58+00:00"


def test_rows_without_session_id_never_mint_a_stage():
    rows = [_row("intelligence.viewed", "", meta={"surface": "flow_velocity",
            "surface_group": "read", "tier_seen": "anon", "rows_visible": 1})]
    rep = AFR.build_report(rows, SINCE, UNTIL, set(), set())
    assert rep["stage_sessions"]["intelligence_viewed"] == 0


def test_report_is_byte_deterministic():
    rows = _full_session("s-det")
    a = json.dumps(AFR.build_report(rows, SINCE, UNTIL, set(), set()), sort_keys=True)
    b = json.dumps(AFR.build_report(list(rows), SINCE, UNTIL, set(), set()), sort_keys=True)
    assert a == b
