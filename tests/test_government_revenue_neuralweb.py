"""Neural Web authority tests for the procurement context lobe."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from engine.neuralweb import mastermind_context as mc


def _write_latest(root: Path) -> None:
    path = root / "data" / "government_revenue" / "latest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "schema_version": "company_government_revenue.v1",
            "as_of": "2026-07-31",
            "known_at": "2026-08-01T08:00:00Z",
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
                "provenance": [{"source": "USAspending"}],
            }],
        }),
        encoding="utf-8",
    )


def test_lobe_is_display_context_with_all_authority_disabled(tmp_path: Path) -> None:
    _write_latest(tmp_path)

    lobe, gap = mc._summarize_government_revenue(tmp_path)

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

    context = mc._build_candidate_context(tmp_path, gaps)

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

    context = mc._build_candidate_context(tmp_path, gaps)

    assert set(context) == {"LMT", "NOC"}
    assert "government_revenue" in context["LMT"]
    assert context["LMT"]["government_revenue"]["allowed_behavior"] == "annotate_only"
    assert not any(context["LMT"]["government_revenue"]["authority"].values())
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
