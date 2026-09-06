"""Tests for engine.chronicle.impact — MO-PAID-017 event-to-asset projection.

Acceptance (MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv row
MO-PAID-017): a consequence surface per event family reads spine output;
calibrated fields absent. Event identity stays spine.py's own (no second
event database); event-time vs known-at are both printed and distinct;
direct vs second-order materiality is labelled; causal labels never exceed
uncalibrated association.
"""
from __future__ import annotations

from engine.chronicle import impact


def _ev(id_, date, ts, source="research_vault", kind="report",
        tickers=None, themes=None):
    return {
        "id": id_, "ts": ts, "date": date, "source": source,
        "source_ref": id_, "kind": kind, "title": "t",
        "facts": [], "tickers": tickers or [], "themes": themes or [],
        "horizon_hint": "medium", "weight_hint": 1,
        "links": {"site": None, "source": None, "receipt": None},
    }


def test_event_identity_is_spine_own_no_second_database():
    ev = _ev("cev-research_vault-abc123", "2026-09-01", "2026-09-01T12:00:00Z",
              tickers=["NVDA"])
    proj = impact.project_event_impact(ev)
    # The projection carries the SAME id spine minted -- it never mints or
    # derives a new identity of its own.
    assert proj["event_id"] == ev["id"]


def test_event_time_vs_known_at_are_distinct_and_printed():
    ev = _ev("cev-x-1", date="2026-08-30", ts="2026-09-01T00:00:00Z", tickers=["AAPL"])
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] == "2026-08-30"
    assert proj["known_at"] == "2026-09-01T00:00:00Z"
    assert proj["event_time"] != proj["known_at"]


def test_direct_materiality_for_named_ticker():
    ev = _ev("cev-x-2", "2026-09-01", "2026-09-01T00:00:00Z", tickers=["MSFT"])
    proj = impact.project_event_impact(ev)
    assert {"ticker": "MSFT", "materiality": "direct"} in proj["exposures"]


def test_second_order_materiality_via_co_theme_never_promoted_to_direct():
    # NVDA is directly named on the earnings event; a research_vault report
    # sharing the "ai_capex" theme but naming no ticker gets NVDA back only
    # as second_order -- never silently upgraded to direct.
    earn = _ev("cev-earnings-1", "2026-09-01", "2026-09-01T00:00:00Z",
                source="earnings", kind="earnings", tickers=["NVDA"],
                themes=["ai_capex"])
    report = _ev("cev-rv-1", "2026-09-02", "2026-09-02T00:00:00Z",
                  source="research_vault", tickers=[], themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact([earn, report])}
    report_proj = projections["cev-rv-1"]
    assert {"ticker": "NVDA", "materiality": "second_order"} in report_proj["exposures"]
    assert not any(e["ticker"] == "NVDA" and e["materiality"] == "direct"
                   for e in report_proj["exposures"])
    earn_proj = projections["cev-earnings-1"]
    assert {"ticker": "NVDA", "materiality": "direct"} in earn_proj["exposures"]


def test_direct_wins_when_ticker_is_both_direct_and_second_order():
    ev = _ev("cev-x-3", "2026-09-01", "2026-09-01T00:00:00Z",
              tickers=["NVDA"], themes=["ai_capex"])
    other = _ev("cev-x-4", "2026-09-01", "2026-09-01T00:00:00Z",
                 tickers=["NVDA"], themes=["ai_capex"])
    projections = impact.project_events_impact([ev, other])
    for proj in projections:
        nvda = [e for e in proj["exposures"] if e["ticker"] == "NVDA"]
        assert nvda == [{"ticker": "NVDA", "materiality": "direct"}]


def test_causal_label_never_exceeds_uncalibrated_association():
    ev = _ev("cev-x-5", "2026-09-01", "2026-09-01T00:00:00Z", tickers=["TSLA"],
              kind="signal_close")
    proj = impact.project_event_impact(ev)
    assert proj["causal_label"] == "uncalibrated_association"
    assert "causal" != proj["causal_label"]


def test_calibrated_impact_absent_and_reason_given_k5_gated():
    ev = _ev("cev-x-6", "2026-09-01", "2026-09-01T00:00:00Z", tickers=["AMZN"])
    proj = impact.project_event_impact(ev)
    assert proj["calibrated_impact"] is None
    assert proj["calibrated_impact_reason"] == "not_yet_knowable_k5_gated"


def test_family_grouping_reads_spine_source_field_per_event_family():
    ev1 = _ev("cev-a-1", "2026-09-01", "2026-09-01T00:00:00Z", source="earnings", tickers=["A"])
    ev2 = _ev("cev-b-1", "2026-09-01", "2026-09-01T00:00:00Z", source="research_vault", tickers=["B"])
    ev3 = _ev("cev-a-2", "2026-09-02", "2026-09-02T00:00:00Z", source="earnings", tickers=["C"])
    families = impact.project_family_impact([ev1, ev2, ev3])
    assert set(families.keys()) == {"earnings", "research_vault"}
    assert len(families["earnings"]) == 2
    assert len(families["research_vault"]) == 1


def test_deterministic_byte_stable_across_repeated_projection():
    events = [
        _ev("cev-a-1", "2026-09-01", "2026-09-01T00:00:00Z", tickers=["A"], themes=["x"]),
        _ev("cev-b-1", "2026-09-02", "2026-09-02T00:00:00Z", tickers=[], themes=["x"]),
    ]
    first = impact.project_events_impact(list(events))
    second = impact.project_events_impact(list(events))
    assert first == second


def test_empty_event_list_yields_no_projections_no_crash():
    assert impact.project_events_impact([]) == []
    assert impact.project_family_impact([]) == {}
