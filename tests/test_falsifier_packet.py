"""Tests for engine/falsifier_packet.py — A1 Falsifier Packet (LHB-W3).

Tests:
  1. Mapping-table determinism: each source state → expected axis status.
  2. A6 routing: 1.03 → broken; 2.04 → challenged (not broken); multi-item rows.
  3. Stale evidence → unverifiable (never no_break_observed).
  4. Vocab closure: every emitted status is in VALID_STATUSES.
  5. Expectation-burden percentile edges (ordinary / stretched / extreme / unverifiable).
  6. Packet includes FFB-R2 coverage copy verbatim.
  7. ARCHETYPE_CARDS structure (6 archetypes, all required keys present).
  8. assemble_packet returns required top-level keys with all sources missing.
"""
from __future__ import annotations

import pytest

from engine.falsifier_packet import (
    ARCHETYPE_CARDS,
    VALID_STATUSES,
    _FFB_R2_COVERAGE_COPY,
    _STALE_EVIDENCE_DAYS,
    _A6_ITEM_ROUTING,
    assemble_packet,
    _moat_sensors_to_axis,
    _funnel_to_sensor,
    _cap_alloc_to_sensor,
    _route_8k_items,
    _compute_ev_sales_percentile,
)


# ---------------------------------------------------------------------------
# Helper: any-date that is fresh (recent) vs stale
# ---------------------------------------------------------------------------

def _fresh_date() -> str:
    """Return a date that is never stale under the 400d rule."""
    from datetime import date, timedelta
    return (date.today() - timedelta(days=10)).isoformat()


def _stale_date() -> str:
    """Return a date older than STALE_EVIDENCE_DAYS."""
    from datetime import date, timedelta
    return (date.today() - timedelta(days=_STALE_EVIDENCE_DAYS + 50)).isoformat()


# ---------------------------------------------------------------------------
# 1. Mapping-table determinism
# ---------------------------------------------------------------------------

class TestMappingTableDeterminism:
    """Each source state maps to exactly one expected status."""

    # --- Moat falsifiers ---

    def test_moat_fired_true_maps_to_challenged(self) -> None:
        result = _moat_sensors_to_axis(
            moat_result={
                "sensor_coverage": "full",
                "margin_compression_despite_revenue_growth": True,
                "receivables_stretch": False,
                "inventory_build": False,
                "capital_intensity_rising": False,
                "sensor_fired_map": {
                    "margin_compression_despite_revenue_growth": True,
                    "receivables_stretch": False,
                    "inventory_build": False,
                    "capital_intensity_rising": False,
                },
            },
            asof_date=_fresh_date(),
        )
        statuses = {s["name"]: s["status"] for s in result}
        assert statuses["Gross-margin compression (moat)"] == "challenged"
        assert statuses["Receivables stretch (moat)"] == "no_break_observed"
        assert statuses["Inventory build (moat)"] == "no_break_observed"
        assert statuses["Capital intensity rising (moat)"] == "no_break_observed"

    def test_moat_fired_false_maps_to_no_break_observed(self) -> None:
        result = _moat_sensors_to_axis(
            moat_result={
                "sensor_coverage": "full",
                "sensor_fired_map": {
                    "margin_compression_despite_revenue_growth": False,
                    "receivables_stretch": False,
                    "inventory_build": False,
                    "capital_intensity_rising": False,
                },
            },
            asof_date=_fresh_date(),
        )
        for s in result:
            assert s["status"] == "no_break_observed", (
                f"Expected no_break_observed for {s['name']}, got {s['status']}"
            )

    def test_moat_coverage_missing_maps_to_unverifiable(self) -> None:
        result = _moat_sensors_to_axis(
            moat_result={"sensor_coverage": "missing"},
            asof_date=_fresh_date(),
        )
        for s in result:
            assert s["status"] == "unverifiable"

    def test_moat_none_result_maps_to_unverifiable(self) -> None:
        result = _moat_sensors_to_axis(moat_result=None, asof_date=None)
        for s in result:
            assert s["status"] == "unverifiable"

    # --- Thesis funnel ---

    def test_funnel_candidate_shadow_maps_to_not_observed(self) -> None:
        s = _funnel_to_sensor({"state": "thesis_candidate_shadow", "as_of": _fresh_date()})
        assert s["status"] == "not_observed"

    def test_funnel_watch_maps_to_not_observed(self) -> None:
        s = _funnel_to_sensor({"state": "watch_for_thesis", "as_of": _fresh_date()})
        assert s["status"] == "not_observed"

    def test_funnel_not_eligible_s4_maps_to_unverifiable(self) -> None:
        s = _funnel_to_sensor({
            "state": "not_eligible",
            "state_reason": "s4_coverage",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "unverifiable"

    def test_funnel_not_eligible_s2_moat_maps_to_challenged(self) -> None:
        s = _funnel_to_sensor({
            "state": "not_eligible",
            "state_reason": "s2_moat_falsifier",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "challenged"

    def test_funnel_not_eligible_s1_dilution_maps_to_challenged(self) -> None:
        s = _funnel_to_sensor({
            "state": "not_eligible",
            "state_reason": "s1_dilution",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "challenged"

    def test_funnel_not_eligible_s3_solvency_maps_to_challenged(self) -> None:
        s = _funnel_to_sensor({
            "state": "not_eligible",
            "state_reason": "s3_solvency",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "challenged"

    def test_funnel_absent_maps_to_unverifiable(self) -> None:
        s = _funnel_to_sensor(None)
        assert s["status"] == "unverifiable"

    # --- Capital allocation ---

    def test_cap_alloc_accretive_maps_to_no_break_observed(self) -> None:
        s = _cap_alloc_to_sensor({
            "capital_allocation_delta": "accretive",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "no_break_observed"

    def test_cap_alloc_neutral_maps_to_not_observed(self) -> None:
        s = _cap_alloc_to_sensor({
            "capital_allocation_delta": "neutral",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "not_observed"

    def test_cap_alloc_dilutive_maps_to_challenged(self) -> None:
        s = _cap_alloc_to_sensor({
            "capital_allocation_delta": "dilutive",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "challenged"

    def test_cap_alloc_unavailable_maps_to_unverifiable(self) -> None:
        s = _cap_alloc_to_sensor({
            "capital_allocation_delta": "unavailable",
            "as_of": _fresh_date(),
        })
        assert s["status"] == "unverifiable"

    def test_cap_alloc_none_maps_to_unverifiable(self) -> None:
        s = _cap_alloc_to_sensor(None)
        assert s["status"] == "unverifiable"


# ---------------------------------------------------------------------------
# 2. A6 routing: Item 1.03 → broken; 2.04 → challenged (not broken)
# ---------------------------------------------------------------------------

class TestA6Routing:
    """A6 hard-stop bus routing rules."""

    def test_item_103_routes_to_broken(self) -> None:
        events = _route_8k_items([{
            "items": "1.03",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000001",
        }])
        assert len(events) == 1
        assert events[0]["item_code"] == "1.03"
        assert events[0]["status"] == "broken"
        assert events[0]["review_label"] == "Verified terminal-risk event"

    def test_item_204_routes_to_challenged_not_broken(self) -> None:
        events = _route_8k_items([{
            "items": "2.04",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000002",
        }])
        assert len(events) == 1
        assert events[0]["item_code"] == "2.04"
        assert events[0]["status"] == "challenged"
        assert events[0]["status"] != "broken"
        assert events[0]["review_label"] == "Solvency review"

    def test_item_102_routes_to_challenged(self) -> None:
        events = _route_8k_items([{
            "items": "1.02",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000003",
        }])
        assert events[0]["status"] == "challenged"
        assert events[0]["review_label"] == "Named-contract review"

    def test_item_502_routes_to_challenged(self) -> None:
        events = _route_8k_items([{
            "items": "5.02",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000004",
        }])
        assert events[0]["status"] == "challenged"
        assert events[0]["review_label"] == "Succession review"

    def test_item_301_routes_to_challenged(self) -> None:
        events = _route_8k_items([{
            "items": "3.01",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000005",
        }])
        assert events[0]["status"] == "challenged"
        assert events[0]["review_label"] == "Financing review"

    def test_item_402_routes_to_challenged(self) -> None:
        events = _route_8k_items([{
            "items": "4.02",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000006",
        }])
        assert events[0]["status"] == "challenged"
        assert events[0]["review_label"] == "Evidence challenged"

    def test_multi_item_row_parses_all(self) -> None:
        """A comma-separated items field produces one entry per routable item."""
        events = _route_8k_items([{
            "items": "1.01,1.02,2.04,5.02",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000007",
        }])
        codes = {e["item_code"] for e in events}
        # 1.01 is not in the A6 routing table
        assert "1.01" not in codes
        assert "1.02" in codes
        assert "2.04" in codes
        assert "5.02" in codes
        # Statuses: all should be challenged (none is 1.03)
        for e in events:
            assert e["status"] == "challenged"

    def test_unrouted_item_not_in_output(self) -> None:
        """Items not in the A6 routing table are silently ignored."""
        events = _route_8k_items([{
            "items": "7.01",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000008",
        }])
        assert len(events) == 0

    def test_empty_events_returns_empty(self) -> None:
        assert _route_8k_items([]) == []
        assert _route_8k_items(None) == []

    def test_accession_and_date_present_in_output(self) -> None:
        events = _route_8k_items([{
            "items": "1.03",
            "filing_date": _fresh_date(),
            "accession": "0001234567-24-000099",
        }])
        assert events[0]["accession"] == "0001234567-24-000099"
        assert events[0]["filing_date"] == _fresh_date()

    def test_stale_challenged_item_dropped(self) -> None:
        """A6 staleness gate: challenged items older than STALE_EVIDENCE_DAYS are dropped."""
        events = _route_8k_items([{
            "items": "5.02",
            "filing_date": _stale_date(),
            "accession": "0001234567-21-000010",
        }])
        assert len(events) == 0, (
            "Stale challenged 5.02 must be dropped; it is a time-sensitive review trigger"
        )

    def test_stale_broken_item_103_kept(self) -> None:
        """Item 1.03 is terminal/permanent — staleness gate does NOT apply."""
        events = _route_8k_items([{
            "items": "1.03",
            "filing_date": _stale_date(),
            "accession": "0001234567-20-000011",
        }])
        assert len(events) == 1
        assert events[0]["status"] == "broken"

    def test_mixed_fresh_challenged_and_stale_challenged(self) -> None:
        """Only fresh challenged items pass; stale ones are silently dropped."""
        events = _route_8k_items([
            {"items": "5.02", "filing_date": _fresh_date(), "accession": "fresh-001"},
            {"items": "3.01", "filing_date": _stale_date(), "accession": "stale-002"},
        ])
        codes = [e["item_code"] for e in events]
        assert "5.02" in codes
        assert "3.01" not in codes

    def test_stale_all_challenged_items_dropped(self) -> None:
        """All non-1.03 routable items respect the staleness gate."""
        challenged_codes = ["1.02", "2.04", "3.01", "3.02", "4.02", "5.02"]
        for code in challenged_codes:
            events = _route_8k_items([{
                "items": code,
                "filing_date": _stale_date(),
                "accession": f"0001-{code}",
            }])
            assert len(events) == 0, (
                f"Stale {code} (challenged) must be dropped by staleness gate"
            )


# ---------------------------------------------------------------------------
# 3. Stale evidence → unverifiable (never no_break_observed)
# ---------------------------------------------------------------------------

class TestStaleEvidence:
    """Stale evidence must map to unverifiable, never no_break_observed (LHB-R3)."""

    def test_stale_moat_asof_maps_to_unverifiable(self) -> None:
        """Fresh-fired sensors with a stale asof → unverifiable."""
        result = _moat_sensors_to_axis(
            moat_result={
                "sensor_coverage": "full",
                "sensor_fired_map": {
                    "margin_compression_despite_revenue_growth": False,
                    "receivables_stretch": False,
                    "inventory_build": False,
                    "capital_intensity_rising": False,
                },
            },
            asof_date=_stale_date(),
        )
        for s in result:
            assert s["status"] == "unverifiable", (
                f"Stale moat sensor should be unverifiable, got {s['status']} for {s['name']}"
            )

    def test_stale_funnel_asof_maps_to_unverifiable(self) -> None:
        """A funnel state with a stale as_of → unverifiable."""
        s = _funnel_to_sensor({
            "state": "thesis_candidate_shadow",
            "as_of": _stale_date(),
        })
        assert s["status"] == "unverifiable", (
            f"Stale funnel should be unverifiable, got {s['status']}"
        )

    def test_stale_cap_alloc_maps_to_unverifiable(self) -> None:
        """Capital allocation with a stale as_of → unverifiable."""
        s = _cap_alloc_to_sensor({
            "capital_allocation_delta": "accretive",
            "as_of": _stale_date(),
        })
        assert s["status"] == "unverifiable", (
            f"Stale cap alloc should be unverifiable, got {s['status']}"
        )

    def test_stale_never_produces_no_break_observed(self) -> None:
        """No stale input must ever produce no_break_observed."""
        # Moat: all fired=False but stale
        result = _moat_sensors_to_axis(
            moat_result={
                "sensor_coverage": "full",
                "sensor_fired_map": {
                    "margin_compression_despite_revenue_growth": False,
                    "receivables_stretch": False,
                    "inventory_build": False,
                    "capital_intensity_rising": False,
                },
            },
            asof_date=_stale_date(),
        )
        for s in result:
            assert s["status"] != "no_break_observed"

        # Cap alloc: accretive but stale
        s = _cap_alloc_to_sensor({
            "capital_allocation_delta": "accretive",
            "as_of": _stale_date(),
        })
        assert s["status"] != "no_break_observed"


# ---------------------------------------------------------------------------
# 4. Vocab closure: every emitted status is in VALID_STATUSES
# ---------------------------------------------------------------------------

class TestVocabClosure:
    """All statuses emitted by assemble_packet must be in VALID_STATUSES."""

    def _collect_statuses(self, packet: dict) -> list[str]:
        statuses = []
        for sensor in packet.get("business_evidence_axis") or []:
            statuses.append(sensor.get("status"))
        for event in packet.get("a6_events") or []:
            statuses.append(event.get("status"))
        return statuses

    def test_packet_with_no_sources_all_unverifiable(self) -> None:
        packet = assemble_packet("TEST", {})
        for status in self._collect_statuses(packet):
            assert status in VALID_STATUSES, f"Invalid status: {status!r}"
        # With no sources, everything should be unverifiable
        for status in self._collect_statuses(packet):
            assert status == "unverifiable"

    def test_packet_with_mixed_sources_all_in_vocab(self) -> None:
        sources = {
            "thesis_funnel_state": {
                "state": "not_eligible",
                "state_reason": "s2_moat_falsifier",
                "as_of": _fresh_date(),
            },
            "capital_allocation_delta": {
                "capital_allocation_delta": "accretive",
                "as_of": _fresh_date(),
            },
            "material_8k_events_rows": [
                {"items": "1.03", "filing_date": _fresh_date(), "accession": "0001-24-000001"},
                {"items": "2.04", "filing_date": _fresh_date(), "accession": "0001-24-000002"},
                {"items": "5.02", "filing_date": _fresh_date(), "accession": "0001-24-000003"},
            ],
        }
        packet = assemble_packet("AAPL", sources)
        for status in self._collect_statuses(packet):
            assert status in VALID_STATUSES, f"Invalid status emitted: {status!r}"

    def test_all_valid_statuses_are_reachable(self) -> None:
        """Sanity: VALID_STATUSES contains exactly the five expected values."""
        assert VALID_STATUSES == frozenset({
            "not_observed",
            "no_break_observed",
            "challenged",
            "broken",
            "unverifiable",
        })

    def test_archetype_cards_do_not_emit_status(self) -> None:
        """ARCHETYPE_CARDS are display/field-guide only; no status field."""
        for card in ARCHETYPE_CARDS:
            assert "status" not in card, (
                f"ARCHETYPE_CARDS must not carry status fields: {card['archetype']}"
            )


# ---------------------------------------------------------------------------
# 5. Expectation-burden percentile edges
# ---------------------------------------------------------------------------

class TestExpectationBurden:
    """EV/sales vs own history classification edges."""

    def _make_statements_df(self, revenues: list[float]):
        """Build a minimal statements DataFrame with the given revenue history."""
        import pandas as pd
        return pd.DataFrame({
            "ticker": ["TEST"] * len(revenues),
            "fy": list(range(2019, 2019 + len(revenues))),
            "revenue": revenues,
        })

    def test_ev_sales_current_computed_correctly(self) -> None:
        # Verify ev_sales_current is computed from current price/shares/net_debt
        # and the latest revenue row.  price=10, shares=1M, net_debt=0 → EV=10M.
        # Latest revenue = 1B → EV/sales = 0.01.
        revenues = [100e6 * i for i in range(1, 11)]  # 100M to 1B, latest = 1B
        df = self._make_statements_df(revenues)
        result = _compute_ev_sales_percentile(
            statements_df=df,
            price=10.0,
            shares=1_000_000,
            net_debt=0.0,
        )
        assert result["ev_sales_current"] == pytest.approx(0.01, rel=1e-3)
        # Percentile is always unverifiable without historical price data
        assert result["burden_label"] == "unverifiable"
        assert result["percentile"] is None

    def test_burden_unverifiable_without_historical_prices(self) -> None:
        # Batch build has only current price; percentile ranking against revenue history
        # alone is valuation-blind (r >= latest_rev, not EV/sales rank) and is NOT
        # reported.  Confirm the axis always returns unverifiable for the percentile
        # and never returns ordinary/stretched/extreme from a misleading revenue rank.
        revenues = [1e6] * 10
        df = self._make_statements_df(revenues)
        for price in [1.0, 100.0, 10_000.0]:
            result = _compute_ev_sales_percentile(
                statements_df=df,
                price=price,
                shares=1_000_000,
                net_debt=0.0,
            )
            assert result["burden_label"] == "unverifiable", (
                f"price={price} produced label={result['burden_label']}; "
                "percentile must be unverifiable in batch build (no historical prices)"
            )
            assert result["percentile"] is None

    def test_insufficient_data_unverifiable(self) -> None:
        # Only 2 revenue rows — below the 3-row minimum
        revenues = [100e6, 200e6]
        df = self._make_statements_df(revenues)
        result = _compute_ev_sales_percentile(
            statements_df=df,
            price=50.0,
            shares=1_000_000,
            net_debt=0.0,
        )
        assert result["burden_label"] == "unverifiable"
        assert result["own_history_n"] == 2

    def test_missing_price_unverifiable(self) -> None:
        revenues = [100e6] * 5
        df = self._make_statements_df(revenues)
        result = _compute_ev_sales_percentile(
            statements_df=df, price=None, shares=1_000_000, net_debt=0.0
        )
        assert result["burden_label"] == "unverifiable"

    def test_none_statements_df_unverifiable(self) -> None:
        result = _compute_ev_sales_percentile(
            statements_df=None, price=50.0, shares=1e6, net_debt=0.0
        )
        assert result["burden_label"] == "unverifiable"

    def test_returns_required_keys(self) -> None:
        revenues = [100e6] * 5
        df = self._make_statements_df(revenues)
        result = _compute_ev_sales_percentile(
            statements_df=df, price=50.0, shares=1e6, net_debt=0.0
        )
        for key in ("ev_sales_current", "own_history_n", "percentile", "burden_label", "note"):
            assert key in result


# ---------------------------------------------------------------------------
# 6. Packet includes FFB-R2 coverage copy verbatim
# ---------------------------------------------------------------------------

class TestFFBR2CoveryCopy:
    """FFB-R2: verbatim coverage copy must appear in every packet header (LHB-W3)."""

    def test_coverage_copy_in_packet(self) -> None:
        packet = assemble_packet("AAPL", {})
        assert "ffb_r2_coverage_copy" in packet
        assert packet["ffb_r2_coverage_copy"] == _FFB_R2_COVERAGE_COPY

    def test_coverage_copy_verbatim_content(self) -> None:
        expected = (
            "Advance review in 7 of 12 studied true breaks; 5 of 12 were visible only "
            "coincident with the break. A6 is a hard-stop bus, not a lead generator."
        )
        assert _FFB_R2_COVERAGE_COPY == expected

    def test_coverage_copy_present_with_full_sources(self) -> None:
        sources = {
            "thesis_funnel_state": {
                "state": "thesis_candidate_shadow",
                "as_of": _fresh_date(),
            },
        }
        packet = assemble_packet("NVDA", sources)
        assert packet["ffb_r2_coverage_copy"] == _FFB_R2_COVERAGE_COPY


# ---------------------------------------------------------------------------
# 7. ARCHETYPE_CARDS structure
# ---------------------------------------------------------------------------

class TestArchetypeCards:
    """ARCHETYPE_CARDS must cover all six archetypes with required keys."""

    _EXPECTED_ARCHETYPES = {
        "quality_compounder",
        "owner_operator",
        "turnaround_distressed",
        "contracted_platform",
        "clinical_milestone",
        "cyclical_commodity",
    }

    _REQUIRED_KEYS = {"archetype", "label", "patience", "trim_review", "exit_review", "cadence"}

    def test_six_archetypes(self) -> None:
        assert len(ARCHETYPE_CARDS) == 6

    def test_archetype_ids_correct(self) -> None:
        actual = {c["archetype"] for c in ARCHETYPE_CARDS}
        assert actual == self._EXPECTED_ARCHETYPES

    def test_required_keys_present_in_all_cards(self) -> None:
        for card in ARCHETYPE_CARDS:
            missing = self._REQUIRED_KEYS - set(card.keys())
            assert not missing, (
                f"Archetype {card.get('archetype')!r} missing keys: {missing}"
            )

    def test_all_string_fields_non_empty(self) -> None:
        for card in ARCHETYPE_CARDS:
            for key in ("patience", "trim_review", "exit_review", "cadence"):
                val = card.get(key)
                assert isinstance(val, str) and len(val.strip()) > 0, (
                    f"Archetype {card['archetype']!r} field {key!r} is empty"
                )


# ---------------------------------------------------------------------------
# 8. assemble_packet top-level shape with all sources missing
# ---------------------------------------------------------------------------

class TestAssemblePacketShape:
    """assemble_packet returns required top-level keys regardless of source availability."""

    _REQUIRED_TOP_LEVEL = {
        "schema",
        "ticker",
        "generated_at",
        "_display_only",
        "_horizon_role",
        "_version",
        "ffb_r2_coverage_copy",
        "a1_questions",
        "business_evidence_axis",
        "a6_events",
        "expectation_burden_axis",
    }

    def test_packet_shape_no_sources(self) -> None:
        packet = assemble_packet("ZZZ", {})
        for key in self._REQUIRED_TOP_LEVEL:
            assert key in packet, f"Missing top-level key: {key!r}"

    def test_display_only_true(self) -> None:
        packet = assemble_packet("AAPL", {})
        assert packet["_display_only"] is True

    def test_horizon_role_hold_thesis(self) -> None:
        packet = assemble_packet("AAPL", {})
        assert packet["_horizon_role"] == "hold_thesis"

    def test_ticker_preserved(self) -> None:
        packet = assemble_packet("GOOGL", {})
        assert packet["ticker"] == "GOOGL"

    def test_schema_correct(self) -> None:
        packet = assemble_packet("MSFT", {})
        assert packet["schema"] == "falsifier_packet.v1"

    def test_a1_questions_five_keys(self) -> None:
        packet = assemble_packet("AMZN", {})
        q = packet["a1_questions"]
        for key in ("q1_entry_clock_expired", "q2_latest_fundamental_confirmation",
                    "q3_falsifiers_fired", "q4_overdue_or_unavailable",
                    "q5_next_evidence_window"):
            assert key in q, f"Missing A1 question key: {key!r}"

    def test_business_evidence_axis_is_list(self) -> None:
        packet = assemble_packet("META", {})
        assert isinstance(packet["business_evidence_axis"], list)

    def test_a6_events_is_list(self) -> None:
        packet = assemble_packet("TSLA", {})
        assert isinstance(packet["a6_events"], list)

    def test_expectation_burden_axis_is_dict(self) -> None:
        packet = assemble_packet("NVDA", {})
        assert isinstance(packet["expectation_burden_axis"], dict)

    def test_sensors_have_required_fields(self) -> None:
        packet = assemble_packet("AAPL", {})
        for sensor in packet["business_evidence_axis"]:
            for field in ("name", "status", "last_observation_date",
                          "evidence_age_days", "cadence_note", "source_key"):
                assert field in sensor, (
                    f"Sensor missing field {field!r}: {sensor.get('name')!r}"
                )

    def test_broken_only_from_103(self) -> None:
        """Verify 1.03 → broken; no other source can produce broken in this packet."""
        sources = {
            "thesis_funnel_state": {
                "state": "not_eligible",
                "state_reason": "s2_moat_falsifier",
                "as_of": _fresh_date(),
            },
            "capital_allocation_delta": {
                "capital_allocation_delta": "dilutive",
                "as_of": _fresh_date(),
            },
            "material_8k_events_rows": [
                {"items": "2.04", "filing_date": _fresh_date(), "accession": "acc-01"},
                {"items": "5.02", "filing_date": _fresh_date(), "accession": "acc-02"},
            ],
        }
        packet = assemble_packet("STRESSED", sources)
        # No 1.03 filed → no broken status anywhere
        all_statuses = [
            s["status"] for s in packet["business_evidence_axis"]
        ] + [e["status"] for e in packet["a6_events"]]
        assert "broken" not in all_statuses

    def test_103_produces_broken(self) -> None:
        """Filing Item 1.03 produces broken in the a6_events."""
        sources = {
            "material_8k_events_rows": [
                {"items": "1.03", "filing_date": _fresh_date(), "accession": "acc-bk"},
            ],
        }
        packet = assemble_packet("BANKRUPT", sources)
        a6_statuses = [e["status"] for e in packet["a6_events"]]
        assert "broken" in a6_statuses
