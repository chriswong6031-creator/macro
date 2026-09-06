"""Tests for engine.chronicle.impact — MO-PAID-017 event-to-asset projection.

Acceptance (MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv row
MO-PAID-017): a consequence surface per event family reads spine output;
calibrated fields absent. Event identity stays spine.py's own (no second
event database); event-time vs known-at are both printed (known_at only
when the source data genuinely supports a distinct clock -- otherwise a
typed null reason, never fabricated); direct vs second-order materiality is
labelled; causal labels never exceed uncalibrated association.

Events are built via schema.new_event (the real assembly path every adapter
uses) rather than hand-rolled dicts, so a spine field rename here fails these
tests instead of leaving them silently green (Major 8).
"""
from __future__ import annotations

from engine.chronicle import impact, schema


def _ev(source_ref, date, ts=None, source="research_vault", kind="report",
        tickers=None, themes=None):
    ts = ts if ts is not None else f"{date}T00:00:00Z"
    return schema.new_event(
        id=schema.make_id(source, source_ref, date),
        ts=ts,
        date=date,
        source=source,
        source_ref=source_ref,
        kind=kind,
        title="t",
        facts=["a fact"],
        tickers=tickers or [],
        themes=themes or [],
        weight_hint=1,
        links=schema.make_links(site="/x.html"),
    )


def test_event_identity_is_spine_own_no_second_database():
    ev = _ev("abc123", "2026-09-01", tickers=["NVDA"])
    proj = impact.project_event_impact(ev)
    # The projection carries the SAME id spine minted -- it never mints or
    # derives a new identity of its own.
    assert proj["event_id"] == ev["id"]


def test_known_at_printed_when_source_gives_a_genuine_distinct_clock():
    # research_vault's real adapter path: ts carries the actual published_at
    # publication time, genuinely distinct from the calendar date.
    ev = _ev("x-1", date="2026-08-30", ts="2026-08-30T14:22:00Z", tickers=["AAPL"])
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] == "2026-08-30"
    assert proj["known_at"] == "2026-08-30T14:22:00Z"
    assert proj["known_at_reason"] is None
    assert proj["event_time"] != proj["known_at"]


def test_known_at_is_null_with_typed_reason_when_ts_is_synthetic_midnight():
    # Every non-timestamped adapter (adapters.py, earnings_calls.py,
    # state_log.py) sets ts=f"{date}T00:00:00Z" -- the SAME instant as
    # event_time, never a real ingestion clock. Printing it as known_at would
    # fabricate a bitemporal claim the ledger explicitly disclaims (Blocker 1).
    ev = _ev("x-2", date="2026-09-01", ts="2026-09-01T00:00:00Z", tickers=["MSFT"])
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] == "2026-09-01"
    assert proj["known_at"] is None
    assert proj["known_at_reason"] == impact.NO_DISTINCT_SOURCE_CLOCK


def test_clockless_event_projects_null_time_fields_with_typed_reason_not_none_silently():
    # Blocker 3: a record with no date and no ts must fail closed with a
    # typed reason, never a bare None with no explanation.
    ev = {"id": "cev-x-clockless", "ts": None, "date": None, "source": "earnings",
          "source_ref": "r", "kind": "earnings", "title": "t", "facts": [],
          "tickers": ["TSLA"], "themes": [], "horizon_hint": "short",
          "weight_hint": 1, "links": {"site": None, "source": None, "receipt": None}}
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] is None
    assert proj["known_at"] is None
    assert proj["known_at_reason"] == impact.NO_SOURCE_CLOCK


def test_direct_materiality_for_named_ticker():
    ev = _ev("x-3", "2026-09-01", tickers=["MSFT"])
    proj = impact.project_event_impact(ev)
    assert {"ticker": "MSFT", "materiality": "direct"} in proj["exposures"]


def test_second_order_requires_minimum_support_and_carries_k1_evidence():
    # NVDA is directly named on TWO prior earnings-family events sharing the
    # ai_capex theme -- meets SECOND_ORDER_MIN_SUPPORT, so a later report
    # sharing that theme (but naming no ticker) gets NVDA as second_order,
    # never silently upgraded to direct, with the originating event ids
    # attached as evidence (Major 5 / K1).
    earn1 = _ev("e1", "2026-08-30", source="earnings", kind="earnings",
                tickers=["NVDA"], themes=["ai_capex"])
    earn2 = _ev("e2", "2026-08-31", source="earnings", kind="earnings",
                tickers=["NVDA"], themes=["ai_capex"])
    report = _ev("r1", "2026-09-02", source="research_vault", tickers=[],
                  themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact([earn1, earn2, report])}
    report_proj = projections[report["id"]]
    nvda_exp = next(e for e in report_proj["exposures"] if e["ticker"] == "NVDA")
    assert nvda_exp["materiality"] == "second_order"
    assert sorted(nvda_exp["source_event_ids"]) == sorted([earn1["id"], earn2["id"]])
    assert not any(e["ticker"] == "NVDA" and e["materiality"] == "direct"
                   for e in report_proj["exposures"])


def test_second_order_needs_minimum_support_single_co_theme_event_is_dropped():
    # Major 4: a SINGLE co-theme event naming a ticker is not enough support
    # to propagate it -- prevents one stray event fanning a ticker onto every
    # sibling under a broad theme.
    earn = _ev("e1", "2026-08-30", source="earnings", tickers=["NVDA"], themes=["ai_capex"])
    report = _ev("r1", "2026-09-01", source="research_vault", tickers=[], themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact([earn, report])}
    assert projections[report["id"]]["exposures"] == []


def test_second_order_is_capped_per_event_and_marks_truncation():
    # Major 4: fan-out is capped, not unbounded (probe D scenario: many
    # tickers sharing one theme must not all land on a ticker-less event).
    supporters = []
    for i in range(SUPPORTERS := 12):
        for _dup in range(2):  # 2x so each ticker clears MIN_SUPPORT
            supporters.append(_ev(f"s{i}-{_dup}", "2026-08-01",
                                    source="earnings", tickers=[f"T{i}"],
                                    themes=["broad"]))
    ticker_less = _ev("tl-1", "2026-09-01", source="research_vault", tickers=[], themes=["broad"])
    projections = {p["event_id"]: p for p in impact.project_events_impact(supporters + [ticker_less])}
    proj = projections[ticker_less["id"]]
    assert len(proj["exposures"]) == impact.SECOND_ORDER_MAX_PER_EVENT
    assert proj["second_order_truncated"] is True
    assert proj["second_order_truncated_reason"] == impact.SECOND_ORDER_CAPPED_REASON


def test_direct_wins_when_ticker_is_both_direct_and_second_order():
    ev = _ev("x-4", "2026-09-01", tickers=["NVDA"], themes=["ai_capex"])
    other1 = _ev("x-5", "2026-08-30", tickers=["NVDA"], themes=["ai_capex"])
    other2 = _ev("x-6", "2026-08-31", tickers=["NVDA"], themes=["ai_capex"])
    projections = impact.project_events_impact([ev, other1, other2])
    ev_proj = next(p for p in projections if p["event_id"] == ev["id"])
    nvda = [e for e in ev_proj["exposures"] if e["ticker"] == "NVDA"]
    assert nvda == [{"ticker": "NVDA", "materiality": "direct"}]


def test_second_order_never_leaks_from_a_future_event_point_in_time():
    # Major 6: an event dated 2026-12-31 must never hand its ticker backward
    # onto an earlier event sharing the theme (point-in-time correctness).
    future = _ev("fut", "2026-12-31", source="earnings", tickers=["NVDA"], themes=["ai_capex"])
    earlier1 = _ev("e1", "2026-08-30", source="earnings", tickers=["AMD"], themes=["ai_capex"])
    earlier2 = _ev("e2", "2026-08-31", source="research_vault", tickers=[], themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact([future, earlier1, earlier2])}
    earlier_proj = projections[earlier2["id"]]
    assert not any(e["ticker"] == "NVDA" for e in earlier_proj["exposures"])


def test_evidence_fields_are_carried_not_dropped():
    # Major 5 (K1): source_ref/links/facts/title must survive the projection
    # so an exposure is never emitted with no way to trace it back.
    ev = _ev("x-7", "2026-09-01", tickers=["AAPL"])
    proj = impact.project_event_impact(ev)
    assert proj["source_ref"] == ev["source_ref"]
    assert proj["links"] == ev["links"]
    assert proj["facts"] == ev["facts"]
    assert proj["title"] == ev["title"]


def test_retracted_event_reports_typed_state_and_empties_exposures():
    # Major 7: a caller marking an event retracted must never see a live
    # exposure survive the projection -- state is explicit, not inferred.
    ev = _ev("x-8", "2026-09-01", tickers=["AAPL"])
    proj = impact.project_event_impact(ev, retracted=True, retraction_reason="quarantined")
    assert proj["state"] == "retracted"
    assert proj["retraction_reason"] == "quarantined"
    assert proj["exposures"] == []


def test_active_event_reports_active_state():
    ev = _ev("x-9", "2026-09-01", tickers=["AAPL"])
    proj = impact.project_event_impact(ev)
    assert proj["state"] == "active"
    assert proj["retraction_reason"] is None


def test_causal_label_never_exceeds_uncalibrated_association():
    ev = _ev("x-10", "2026-09-01", tickers=["TSLA"], kind="signal_close")
    proj = impact.project_event_impact(ev)
    assert proj["causal_label"] == "uncalibrated_association"
    assert "causal" != proj["causal_label"]


def test_calibrated_impact_absent_and_reason_given_k5_gated():
    ev = _ev("x-11", "2026-09-01", tickers=["AMZN"])
    proj = impact.project_event_impact(ev)
    assert proj["calibrated_impact"] is None
    assert proj["calibrated_impact_reason"] == "not_yet_knowable_k5_gated"


def test_family_grouping_reads_spine_source_field_per_event_family():
    ev1 = _ev("a-1", "2026-09-01", source="earnings", tickers=["A"])
    ev2 = _ev("b-1", "2026-09-01", source="research_vault", tickers=["B"])
    ev3 = _ev("a-2", "2026-09-02", source="earnings", tickers=["C"])
    families = impact.project_family_impact([ev1, ev2, ev3])
    assert set(families.keys()) == {"earnings", "research_vault"}
    assert len(families["earnings"]) == 2
    assert len(families["research_vault"]) == 1


def test_deterministic_byte_stable_across_repeated_projection():
    events = [
        _ev("a-1", "2026-09-01", tickers=["A"], themes=["x"]),
        _ev("b-1", "2026-09-02", tickers=[], themes=["x"]),
    ]
    first = impact.project_events_impact(list(events))
    second = impact.project_events_impact(list(events))
    assert first == second


def test_empty_event_list_yields_no_projections_no_crash():
    assert impact.project_events_impact([]) == []
    assert impact.project_family_impact([]) == {}


def test_write_family_impact_persists_real_consumer_artifact(tmp_path):
    # Blocker 2: impact.py has a real reader/writer path, not just tests --
    # governor.build_and_write calls this exact function.
    ev = _ev("a-1", "2026-09-01", source="earnings", tickers=["A"])
    families = impact.project_family_impact([ev])
    path = impact.write_family_impact(tmp_path, families)
    assert path.exists()
    import json
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert lines[0]["family"] == "earnings"
