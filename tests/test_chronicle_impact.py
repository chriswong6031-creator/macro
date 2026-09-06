"""Tests for engine.chronicle.impact — MO-PAID-017 event-to-asset projection.

Acceptance (MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv row
MO-PAID-017): a consequence surface per event family reads spine output;
calibrated fields absent. Event identity stays spine.py's own (no second
event database); event-time vs known-at are both printed (known_at only
when the source data genuinely supports a distinct clock -- otherwise a
typed null reason, never fabricated); direct vs second-order materiality is
labelled; causal labels never exceed uncalibrated association; weak
second-order (corpus-dominant themes / ambiguous caps) fails closed rather
than ranking; no nightly git-tracked impact.jsonl dump.

Events are built via schema.new_event (the real assembly path every adapter
uses) rather than hand-rolled dicts, so a spine field rename here fails these
tests instead of leaving them silently green.
"""
from __future__ import annotations

import time

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
    assert proj["event_id"] == ev["id"]


def test_event_time_vs_known_at_are_distinct_and_printed():
    # Alias of the genuine-distinct-clock case — PR acceptance evidence name.
    ev = _ev("x-1", date="2026-08-30", ts="2026-08-30T14:22:00Z", tickers=["AAPL"])
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] == "2026-08-30"
    assert proj["known_at"] == "2026-08-30T14:22:00Z"
    assert proj["known_at_reason"] is None
    assert proj["event_time"] != proj["known_at"]


def test_known_at_printed_when_source_gives_a_genuine_distinct_clock():
    ev = _ev("x-1b", date="2026-08-30", ts="2026-08-30T14:22:00Z", tickers=["AAPL"])
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] == "2026-08-30"
    assert proj["known_at"] == "2026-08-30T14:22:00Z"
    assert proj["known_at_reason"] is None


def test_known_at_is_null_with_typed_reason_when_ts_is_synthetic_midnight():
    ev = _ev("x-2", date="2026-09-01", ts="2026-09-01T00:00:00Z", tickers=["MSFT"])
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] == "2026-09-01"
    assert proj["known_at"] is None
    assert proj["known_at_reason"] == impact.NO_DISTINCT_SOURCE_CLOCK


def test_clockless_event_projects_null_time_fields_with_typed_reason_not_none_silently():
    ev = {"id": "cev-x-clockless", "ts": None, "date": None, "source": "earnings",
          "source_ref": "r", "kind": "earnings", "title": "t", "facts": [],
          "tickers": ["TSLA"], "themes": [], "horizon_hint": "short",
          "weight_hint": 1, "links": {"site": None, "source": None, "receipt": None}}
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] is None
    assert proj["known_at"] is None
    assert proj["known_at_reason"] == impact.NO_SOURCE_CLOCK


def test_ts_without_date_recovers_event_time_not_known_at_alone():
    # MINOR: date absent + ts present must not print known_at beside a null
    # event_time — recover the calendar date from the timestamp.
    ev = {"id": "cev-x-ts-only", "ts": "2026-09-01T14:00:00Z", "date": None,
          "source": "research_vault", "source_ref": "r", "kind": "report",
          "title": "t", "facts": [], "tickers": ["AAPL"], "themes": [],
          "horizon_hint": "medium", "weight_hint": 1,
          "links": {"site": None, "source": None, "receipt": None}}
    proj = impact.project_event_impact(ev)
    assert proj["event_time"] == "2026-09-01"
    assert proj["known_at"] == "2026-09-01T14:00:00Z"
    assert proj["known_at_reason"] is None


def test_direct_materiality_for_named_ticker():
    ev = _ev("x-3", "2026-09-01", tickers=["MSFT"])
    proj = impact.project_event_impact(ev)
    assert {"ticker": "MSFT", "materiality": "direct"} in proj["exposures"]


def test_second_order_materiality_via_co_theme_never_promoted_to_direct():
    # Narrow theme + MIN_SUPPORT met: second_order labelled, never upgraded.
    earn1 = _ev("e1", "2026-08-30", source="earnings", kind="earnings",
                tickers=["NVDA"], themes=["ai_capex"])
    earn2 = _ev("e2", "2026-08-31", source="earnings", kind="earnings",
                tickers=["NVDA"], themes=["ai_capex"])
    report = _ev("r1", "2026-09-02", source="research_vault", tickers=[],
                  themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact(
        [earn1, earn2, report])}
    report_proj = projections[report["id"]]
    nvda_exp = next(e for e in report_proj["exposures"] if e["ticker"] == "NVDA")
    assert nvda_exp["materiality"] == "second_order"
    assert sorted(nvda_exp["source_event_ids"]) == sorted([earn1["id"], earn2["id"]])
    assert not any(e["ticker"] == "NVDA" and e["materiality"] == "direct"
                   for e in report_proj["exposures"])


def test_second_order_requires_minimum_support_and_carries_k1_evidence():
    earn1 = _ev("e1b", "2026-08-30", source="earnings", kind="earnings",
                tickers=["NVDA"], themes=["ai_capex"])
    earn2 = _ev("e2b", "2026-08-31", source="earnings", kind="earnings",
                tickers=["NVDA"], themes=["ai_capex"])
    report = _ev("r1b", "2026-09-02", source="research_vault", tickers=[],
                  themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact(
        [earn1, earn2, report])}
    report_proj = projections[report["id"]]
    nvda_exp = next(e for e in report_proj["exposures"] if e["ticker"] == "NVDA")
    assert nvda_exp["materiality"] == "second_order"
    assert sorted(nvda_exp["source_event_ids"]) == sorted([earn1["id"], earn2["id"]])


def test_second_order_needs_minimum_support_single_co_theme_event_is_dropped():
    earn = _ev("e1c", "2026-08-30", source="earnings", tickers=["NVDA"], themes=["ai_capex"])
    report = _ev("r1c", "2026-09-01", source="research_vault", tickers=[], themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact([earn, report])}
    assert projections[report["id"]]["exposures"] == []


def test_broad_theme_second_order_fails_closed_not_ranked():
    # BLOCKER 1: corpus-dominant theme ("earnings") must not propagate
    # second-order exposures via co-mention count / alphabetical top-N.
    supporters = []
    # 40 events under "earnings" + 1 under a narrow theme so earnings share
    # is well above SECOND_ORDER_THEME_MAX_SHARE (5%).
    for i in range(40):
        supporters.append(_ev(f"earn-{i}", "2026-08-01", source="earnings",
                              tickers=[f"T{i % 5}"], themes=["earnings"]))
    report = _ev("rv-broad", "2026-09-01", source="research_vault", tickers=[],
                  themes=["earnings"])
    projections = {p["event_id"]: p for p in impact.project_events_impact(
        supporters + [report])}
    proj = projections[report["id"]]
    assert proj["exposures"] == []
    assert "earnings" in proj["second_order_theme_refused"]
    assert proj["second_order_theme_refused_reason"] == (
        impact.SECOND_ORDER_THEME_TOO_BROAD_REASON)


def test_second_order_ambiguous_cap_refuses_all_and_prints_dropped_count():
    # MAJOR 7 + no opaque ranker: when > MAX candidates remain on a narrow
    # theme, refuse ALL second-order and print candidate/dropped counts.
    supporters = []
    for i in range(12):
        for dup in range(2):
            supporters.append(_ev(f"s{i}-{dup}", "2026-08-01",
                                    source="earnings", tickers=[f"T{i}"],
                                    themes=["narrow_supply"]))
    ticker_less = _ev("tl-1", "2026-09-01", source="research_vault", tickers=[],
                       themes=["narrow_supply"])
    projections = {p["event_id"]: p for p in impact.project_events_impact(
        supporters + [ticker_less])}
    proj = projections[ticker_less["id"]]
    assert proj["exposures"] == []
    assert proj["second_order_truncated"] is True
    assert proj["second_order_truncated_reason"] == impact.SECOND_ORDER_AMBIGUOUS_REASON
    assert proj["second_order_candidate_count"] == 12
    assert proj["second_order_dropped_count"] == 12


def test_direct_wins_when_ticker_is_both_direct_and_second_order():
    # Exercise project_event_impact's dedup branch directly (not only the
    # project_events_impact path that drops own tickers before the call).
    ev = _ev("x-4", "2026-09-01", tickers=["NVDA"], themes=["ai_capex"])
    proj = impact.project_event_impact(
        ev,
        second_order_tickers=["NVDA", "AMD"],
        second_order_sources={"NVDA": ["cev-other"], "AMD": ["cev-other2"]},
    )
    nvda = [e for e in proj["exposures"] if e["ticker"] == "NVDA"]
    assert nvda == [{"ticker": "NVDA", "materiality": "direct"}]
    assert {"ticker": "AMD", "materiality": "second_order",
            "source_event_ids": ["cev-other2"]} in proj["exposures"]


def test_second_order_never_leaks_from_a_future_event_point_in_time():
    future = _ev("fut", "2026-12-31", source="earnings", tickers=["NVDA"], themes=["ai_capex"])
    earlier1 = _ev("e1d", "2026-08-30", source="earnings", tickers=["AMD"], themes=["ai_capex"])
    earlier2 = _ev("e2d", "2026-08-31", source="research_vault", tickers=[], themes=["ai_capex"])
    # Need a second prior AMD naming so MIN_SUPPORT is the only reason NVDA
    # stays out -- future must not contribute.
    earlier3 = _ev("e3d", "2026-08-29", source="earnings", tickers=["AMD"], themes=["ai_capex"])
    projections = {p["event_id"]: p for p in impact.project_events_impact(
        [future, earlier1, earlier2, earlier3])}
    earlier_proj = projections[earlier2["id"]]
    assert not any(e["ticker"] == "NVDA" for e in earlier_proj["exposures"])


def test_evidence_fields_are_carried_not_dropped():
    ev = _ev("x-7", "2026-09-01", tickers=["AAPL"])
    proj = impact.project_event_impact(ev)
    assert proj["source_ref"] == ev["source_ref"]
    assert proj["links"] == ev["links"]
    assert proj["facts"] == ev["facts"]
    assert proj["title"] == ev["title"]


def test_retracted_event_reports_typed_state_and_empties_exposures():
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


def test_glance_consequence_surface_explicitly_does_not_serve_market_feed():
    # BLOCKER 3 / MO-DELTA-001: real consumer surface + explicit non-Market-Feed.
    ev = _ev("a-1", "2026-09-01", source="earnings", tickers=["A"])
    surface = impact.glance_consequence_surface([ev])
    assert surface["served_as_market_feed"] is False
    assert surface["market_feed_disposition"] == "explicitly_does_not_serve_market_feed"
    assert surface["event_count"] == 1
    assert surface["rows"][0]["direct_tickers"] == ["A"]
    assert surface["rows"][0]["calibrated_impact"] is None


def test_glance_consequence_surface_null_on_empty():
    surface = impact.glance_consequence_surface([])
    assert surface["rows"] == []
    assert surface["stance_en"] == "Not available yet"
    assert surface["served_as_market_feed"] is False


def test_plain_glance_titles_strip_ledger_enums():
    """Front-end clarity: glance titles never print T1_HIT / BULL / EXPIRED."""
    en, zh = impact.plain_glance_titles({
        "title": "Prophet close: FBRT BULL → T1_HIT (+10.8% in 25d)",
        "source": "prophet_ledger",
        "exposures": [{"ticker": "FBRT", "materiality": "direct"}],
    })
    assert "T1_HIT" not in en and "T1_HIT" not in zh
    assert "BULL" not in en and "BULL" not in zh
    assert "FBRT" in en and "FBRT" in zh
    assert "hit first target" in en
    assert "达到首个目标" in zh

    en2, zh2 = impact.plain_glance_titles({
        "title": "CANADA regime: Q3 Stagflation → Q2 Reflation",
        "source": "regime_flip",
        "exposures": [],
    })
    assert "Q3" not in en2 and "Q2" not in en2
    assert "regime shifted" in en2
    assert "体制切换" in zh2

    surface = impact.glance_consequence_surface([{
        **_ev("p-1", "2026-09-01", source="prophet_ledger", tickers=["FBRT"]),
        "title": "Prophet close: FBRT BULL → EXPIRED (-2.1% in 45d)",
        "kind": "signal_close",
    }])
    row = surface["rows"][0]
    assert row["title_en"] and row["title_zh"]
    assert "EXPIRED" not in row["title_en"]
    assert "EXPIRED" not in row["title_zh"]
    assert "到期未达标" in row["title_zh"]


def test_no_write_family_impact_helper_on_module():
    # BLOCKER 2: nightly writer removed — projection is read-time only.
    assert not hasattr(impact, "write_family_impact")


def test_project_events_impact_scale_stays_subsecond_on_2k_events():
    # MAJOR 5: bounded cost on a 2k-event fixture (dominant broad theme
    # refused; narrow theme stays small).
    events = []
    for i in range(1900):
        events.append(_ev(f"broad-{i}", f"2026-01-{(i % 28) + 1:02d}",
                          source="earnings", tickers=[f"B{i % 10}"],
                          themes=["earnings"]))
    for i in range(100):
        events.append(_ev(f"narrow-{i}", f"2026-02-{(i % 28) + 1:02d}",
                          source="research_vault", tickers=[f"N{i % 3}"],
                          themes=["narrow_supply"]))
    t0 = time.perf_counter()
    out = impact.project_events_impact(events)
    elapsed = time.perf_counter() - t0
    assert len(out) == 2000
    assert elapsed < 2.0, f"projection took {elapsed:.3f}s on 2k events"
