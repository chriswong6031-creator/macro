"""Neural Web authority tests for the procurement context lobe."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from engine.neuralweb import mastermind_context as mc


def _write_latest(
    root: Path,
    *,
    status: str = "ok",
    opportunity_status: str = "ok",
) -> None:
    path = root / "data" / "government_revenue" / "latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "schema_version": "company_government_revenue.v1",
            "as_of": "2026-07-31",
            "known_at": "2026-08-01T11:00:00Z",
            "freshness": {
                "status": status,
                "aggregate": {
                    "status": "ok",
                    "known_at": "2026-08-01T11:00:00Z",
                    "freshness_sla_days": 35,
                },
                "award_detail": {
                    "status": "ok",
                    "observed_at": "2026-08-01T11:00:00Z",
                    "freshness_sla_days": 4,
                },
                "actions": {
                    "status": "ok",
                    "observed_at": "2026-08-01T11:00:00Z",
                    "freshness_sla_days": 4,
                },
                "opportunities": {
                    "status": opportunity_status,
                    "observed_at": "2026-08-01T11:00:00Z",
                    "freshness_sla_minutes": 90,
                },
            },
            "workbench": {"id": "government_revenue", "desk": "procurement"},
            "coverage": {"entities_mapped": 1},
            "market": {
                "ttm_obligations": 10_000_000_000,
                "companies_with_award_detail": 0,
                "latest_complete_month": "2026-05",
                "award_velocity_breadth": {"accelerating": 1},
            },
            "companies": [{
                "ticker": "LMT",
                "metrics": {
                    "ttm_obligations": 10_000_000_000,
                    "award_velocity_yoy_pct": 12.5,
                    "latest_complete_month": "2026-05",
                },
                "catalyst_facts": [{"headline": "Award pace accelerated"}],
                "opportunity_candidates": [{
                    "notice_id": "opp-1",
                    "title": "Hypersonic interceptor sustainment",
                    "known_at": "2026-08-01T07:00:00Z",
                    "source_url": "https://sam.gov/opp/opp-1/view",
                    "match": {
                        "evidence_class": "rule_based_exposure_candidate",
                        "label_limit": "not a bidder probability, award forecast, or revenue estimate",
                    },
                }],
                "provenance": [{"source": "USAspending"}],
            }],
        }),
        encoding="utf-8",
    )


def test_lobe_is_display_context_with_all_authority_disabled(tmp_path: Path) -> None:
    _write_latest(tmp_path)

    lobe, gap = mc._summarize_government_revenue(
        tmp_path, now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    )

    assert gap is None
    assert lobe["is_context_only"] is True
    assert lobe["display_only"] is True
    assert not any(lobe["authority"].values())
    assert lobe["coverage"]["companies"] == 1
    assert lobe["coverage"]["detailed_companies"] == 0
    assert lobe["market"]["accelerating_companies"] == 1


def test_procurement_data_cannot_create_neural_web_candidate(tmp_path: Path) -> None:
    _write_latest(tmp_path)
    gaps: list[str] = []

    context = mc._build_candidate_context(
        tmp_path,
        gaps,
        now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
    )

    assert context == {}


def test_procurement_context_attaches_only_to_existing_candidate(tmp_path: Path) -> None:
    _write_latest(tmp_path)
    standouts = tmp_path / "site" / "factordata" / "us_standouts.json"
    standouts.parent.mkdir(parents=True)
    standouts.write_text(
        json.dumps({"buy": [{"ticker": "LMT"}, {"ticker": "NOC"}], "watch": [], "laggards": []}),
        encoding="utf-8",
    )
    gaps: list[str] = []

    context = mc._build_candidate_context(
        tmp_path,
        gaps,
        now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
    )

    assert set(context) == {"LMT", "NOC"}
    assert "government_revenue" in context["LMT"]
    assert context["LMT"]["government_revenue"]["allowed_behavior"] == "annotate_only"
    assert not any(context["LMT"]["government_revenue"]["authority"].values())
    assert context["LMT"]["government_revenue"]["opportunity_candidates"][0]["notice_id"] == "opp-1"
    assert "government_revenue" not in context["NOC"]


def test_full_context_registers_procurement_source_and_freshness(tmp_path: Path) -> None:
    _write_latest(tmp_path)

    payload = mc.build_context(
        tmp_path, now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    )

    assert "data/government_revenue/latest.json" in payload["source_artifacts"]
    assert payload["freshness"]["government_revenue"]["as_of"] == "2026-07-31"
    assert isinstance(payload["freshness"]["government_revenue"]["stale"], bool)


def test_historical_neural_replay_cannot_see_future_procurement_snapshot(
    tmp_path: Path,
) -> None:
    _write_latest(tmp_path)
    standouts = tmp_path / "site" / "factordata" / "us_standouts.json"
    standouts.parent.mkdir(parents=True)
    standouts.write_text(
        json.dumps({"buy": [{"ticker": "LMT"}], "watch": [], "laggards": []}),
        encoding="utf-8",
    )

    payload = mc.build_context(
        tmp_path, now=datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    )

    assert payload["lobes"]["government_revenue"] == {}
    assert "government_revenue" not in payload["candidate_context"]["LMT"]
    assert any("newer than replay" in note for note in payload["gap_notes"])


def test_degraded_procurement_snapshot_cannot_annotate_neural_candidates(
    tmp_path: Path,
) -> None:
    _write_latest(tmp_path, status="stale")
    standouts = tmp_path / "site" / "factordata" / "us_standouts.json"
    standouts.parent.mkdir(parents=True)
    standouts.write_text(
        json.dumps({"buy": [{"ticker": "LMT"}], "watch": [], "laggards": []}),
        encoding="utf-8",
    )

    payload = mc.build_context(
        tmp_path, now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    )

    lobe = payload["lobes"]["government_revenue"]
    assert lobe["degraded"] is True
    assert lobe["freshness"]["status"] == "stale"
    assert lobe["market"] == {}
    assert "government_revenue" not in payload["candidate_context"]["LMT"]
    assert any("company facts suppressed" in note for note in payload["gap_notes"])


def test_stale_opportunity_rail_suppresses_only_opportunity_candidates(
    tmp_path: Path,
) -> None:
    _write_latest(tmp_path, opportunity_status="stale")
    gaps: list[str] = []

    context = mc._load_government_revenue_map(
        tmp_path,
        gaps,
        now=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
    )

    assert context["LMT"]["freshness"]["opportunities"] == "stale"
    assert context["LMT"]["opportunity_candidates"] == []
    assert context["LMT"]["metrics"]["award_velocity_yoy_pct"] == 12.5
    assert any("opportunity candidates suppressed" in note for note in gaps)


def test_elapsed_source_sla_suppresses_once_ok_procurement_context(tmp_path: Path) -> None:
    _write_latest(tmp_path)
    gaps: list[str] = []

    context = mc._load_government_revenue_map(
        tmp_path,
        gaps,
        now=datetime(2026, 8, 10, 12, tzinfo=timezone.utc),
    )

    assert context == {}
    assert any("freshness stale" in note for note in gaps)
