from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from engine.intelligence_workspace.adapters.company_intelligence import (
    CompanyIntelligenceAdapter,
)
from engine.intelligence_workspace.adapters.earnings import EarningsCalendarAdapter
from engine.intelligence_workspace.adapters.industry import IndustryAdapter
from engine.intelligence_workspace.adapters.stage import StageAdapter
from engine.intelligence_workspace.adapters.theme import ThemeAdapter
from engine.intelligence_workspace.contracts import CanonicalEntity
from engine.intelligence_workspace.projection import ThemeRightsProjector
from engine.intelligence_workspace.registry import load_registry
from engine.intelligence_workspace.resolver import DatapointResolver


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
AAPL = "SEC:US-XNAS-AAPL"
MSFT = "SEC:US-XNAS-MSFT"


class FixedIdentity:
    def normalize_many(self, entities):
        return tuple(
            CanonicalEntity(
                entity.type,
                str(entity.id),
                entity.universe or ("us_equity" if entity.type == "security" else "us_industry"),
            )
            for entity in entities
        )


def _resolve(
    adapter_id: str,
    adapter: Any,
    *,
    field_ids: list[str],
    entities: list[dict[str, str]],
    audience: str = "internal",
    rights_projector=None,
):
    resolver = DatapointResolver(
        registry=load_registry(),
        identity_normalizer=FixedIdentity(),
        adapters={adapter_id: adapter},
        rights_projector=rights_projector,
        clock=lambda: NOW,
    )
    return resolver.resolve(
        {
            "entities": entities,
            "field_ids": field_ids,
            "audience": audience,
            "consumer_use": "query",
        }
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _security(entity_id: str = AAPL) -> dict[str, str]:
    return {"type": "security", "id": entity_id, "universe": "us_equity"}


@pytest.mark.parametrize("stage", [0, 1, 2, 3, 4])
def test_stage_zero_is_typed_absence_and_one_through_four_are_owner_values(
    tmp_path: Path, stage: int
) -> None:
    _write_json(
        tmp_path / "data/stage_analysis/screener.json",
        {
            "schema": "stage_screener.v1",
            "asof": "2026-08-23",
            "built": "2026-08-23T03:55:25Z",
            "stage_week_end": "2026-08-21",
            "rows": [
                {
                    "ticker": "AAPL",
                    "source": "live",
                    "stage": stage,
                    "weeks_in_stage": 7,
                    "stage_current": True,
                    "fresh": True,
                    "stage_source_asof": "2026-08-21",
                    "stage_week_end": "2026-08-21",
                }
            ],
        },
    )
    calls = {"symbols": 0, "artifact": 0}

    def symbols():
        calls["symbols"] += 1
        return {AAPL: "AAPL"}

    adapter = StageAdapter(repo_root=tmp_path, symbol_map_loader=symbols)
    original_load = adapter._load_document

    def load_document():
        calls["artifact"] += 1
        return original_load()

    adapter._load_document = load_document  # type: ignore[method-assign]
    got = _resolve(
        "stage",
        adapter,
        field_ids=["stage.current", "stage.weeks_in_stage"],
        entities=[_security()],
    )
    assert calls == {"symbols": 1, "artifact": 1}
    if stage == 0:
        assert [(row["status"], row["reason_code"], row["value"]) for row in got] == [
            ("not_applicable", "not_applicable", None),
            ("not_applicable", "not_applicable", None),
        ]
    else:
        assert [row["value"] for row in got] == [stage, 7]
        assert all(row["status"] == "available" for row in got)
    assert all(row["source"]["owner"] == "stage_analysis" for row in got)
    assert all(row["source"]["dataset_id"] is None for row in got)


def test_stage_owner_current_false_is_typed_stale(tmp_path: Path) -> None:
    row = {
        "ticker": "AAPL",
        "source": "live",
        "stage": 2,
        "weeks_in_stage": 4,
        "stage_source_asof": "2026-08-08",
        "stage_week_end": "2026-08-08",
        "fresh": True,
        "stage_current": False,
    }
    _write_json(
        tmp_path / "data/stage_analysis/screener.json",
        {
            "asof": "2026-08-23",
            "built": "2026-08-23T03:55:25Z",
            "stage_week_end": "2026-08-21",
            "rows": [row],
        },
    )
    got = _resolve(
        "stage",
        StageAdapter(repo_root=tmp_path, symbol_map_loader=lambda: {AAPL: "AAPL"}),
        field_ids=["stage.current"],
        entities=[_security()],
    )[0]
    assert (got["status"], got["reason_code"], got["value"]) == (
        "stale",
        "owner_stale",
        None,
    )
    assert got["freshness"]["state"] == "stale"


def test_stage_setup_fresh_false_is_not_data_recency(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data/stage_analysis/screener.json",
        {
            "asof": "2026-08-23",
            "built": "2026-08-23T03:55:25Z",
            "stage_week_end": "2026-08-21",
            "rows": [
                {
                    "ticker": "AAPL",
                    "source": "live",
                    "stage": 2,
                    "weeks_in_stage": 46,
                    "stage_source_asof": "2026-08-21",
                    "stage_week_end": "2026-08-21",
                    "stage_current": True,
                    "fresh": False,
                }
            ],
        },
    )
    got = _resolve(
        "stage",
        StageAdapter(repo_root=tmp_path, symbol_map_loader=lambda: {AAPL: "AAPL"}),
        field_ids=["stage.current", "stage.weeks_in_stage"],
        entities=[_security()],
    )
    assert [(row["status"], row["value"]) for row in got] == [
        ("available", 2),
        ("available", 46),
    ]


def test_industry_rank_and_member_percentile_are_distinct_owner_reads(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data/stage_analysis/industry_ranks.json",
        {
            "schema": "stage_industry_ranks.v1",
            "asof": "2026-08-23",
            "built": "2026-08-23T04:00:00Z",
            "status": "ready",
            "coverage": {"status": "ready", "freshness": {"status": "current"}},
            "regions": {
                "USA": [
                    {"region": "USA", "industry_id": "software", "industry_percentile": 72.0}
                ]
            },
        },
    )
    _write_json(
        tmp_path / "data/stage_analysis/industry_name_pctile.json",
        {
            "schema": "stage_industry_name_pctile.v1",
            "asof": "2026-08-23",
            "built": "2026-08-23T04:01:00Z",
            "status": "ready",
            "coverage": {"status": "ready", "freshness": {"status": "current"}},
            "percentiles": {"AAPL": 19.0},
        },
    )
    adapter = IndustryAdapter(
        repo_root=tmp_path,
        symbol_map_loader=lambda: {AAPL: "AAPL"},
    )
    rank = _resolve(
        "industry",
        adapter,
        field_ids=["industry.rank.percentile"],
        entities=[{"type": "industry", "id": "software", "universe": "us_industry"}],
    )[0]
    member = _resolve(
        "industry",
        adapter,
        field_ids=["security.industry_member.rs_percentile"],
        entities=[_security()],
    )[0]
    assert rank["value"] == 72.0
    assert member["value"] == 19.0
    assert rank["source"]["source_id"] == "stage_industry.industry_ranks"
    assert member["source"]["source_id"] == "stage_industry.industry_name_pctile"
    assert rank["provenance"]["owner_field_key"] == "industry_rank_percentile"
    assert member["provenance"]["owner_field_key"] == "member_rs_percentile"


def test_industry_owner_stale_never_emits_a_percentile(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data/stage_analysis/industry_name_pctile.json",
        {
            "asof": "2026-08-01",
            "built": "2026-08-01T04:01:00Z",
            "status": "warn",
            "coverage": {"status": "warn", "freshness": {"status": "stale"}},
            "percentiles": {"AAPL": 0.0},
        },
    )
    got = _resolve(
        "industry",
        IndustryAdapter(repo_root=tmp_path, symbol_map_loader=lambda: {AAPL: "AAPL"}),
        field_ids=["security.industry_member.rs_percentile"],
        entities=[_security()],
    )[0]
    assert (got["status"], got["value"], got["reason_code"]) == (
        "stale",
        None,
        "owner_stale",
    )


def test_industry_current_warn_coverage_fails_closed_owner_degraded(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data/stage_analysis/industry_name_pctile.json",
        {
            "asof": "2026-08-23",
            "built": "2026-08-23T04:01:00Z",
            "status": "warn",
            "coverage": {"status": "warn", "freshness": {"status": "current"}},
            "percentiles": {"AAPL": 50.0},
        },
    )
    got = _resolve(
        "industry",
        IndustryAdapter(repo_root=tmp_path, symbol_map_loader=lambda: {AAPL: "AAPL"}),
        field_ids=["security.industry_member.rs_percentile"],
        entities=[_security()],
    )[0]
    assert (got["status"], got["value"], got["reason_code"]) == (
        "unavailable",
        None,
        "owner_degraded",
    )


def test_earnings_uses_each_rows_own_as_of_and_loads_owner_once() -> None:
    frame = pd.DataFrame(
        [
            {"ticker": "AAPL", "next_date": "2026-10-29", "as_of": "2026-07-01T01:00:00Z"},
            {"ticker": "MSFT", "next_date": "2026-10-30", "as_of": "2026-08-22T01:00:00Z"},
        ]
    )
    calls = {"frame": 0, "symbols": 0}
    assessed: list[tuple[str, ...]] = []

    def load_frame():
        calls["frame"] += 1
        return frame

    def load_symbols():
        calls["symbols"] += 1
        return {AAPL: "AAPL", MSFT: "MSFT"}

    def assess(rows, *, today):
        assert today == NOW.date()
        assessed.append(tuple(rows["ticker"]))
        return {"stale": int(str(rows.iloc[0]["as_of"]).startswith("2026-07"))}

    got = _resolve(
        "earnings_calendar",
        EarningsCalendarAdapter(
            dataframe_loader=load_frame,
            symbol_map_loader=load_symbols,
            staleness_assessor=assess,
        ),
        field_ids=["earnings.next_date"],
        entities=[_security(AAPL), _security(MSFT)],
    )
    assert calls == {"frame": 1, "symbols": 1}
    assert assessed == [("AAPL",), ("MSFT",)]
    assert (got[0]["status"], got[0]["value"], got[0]["as_of"]) == (
        "stale",
        None,
        "2026-07-01T01:00:00Z",
    )
    assert (got[1]["status"], got[1]["value"], got[1]["as_of"]) == (
        "available",
        "2026-10-30",
        "2026-08-22T01:00:00Z",
    )
    assert got[1]["effective_at"] == "2026-10-30"


def test_company_intelligence_preserves_each_metric_lineage_and_event_clock() -> None:
    calls: list[dict[str, Any]] = []

    def read(request):
        calls.append(dict(request))
        return {
            "available": True,
            "status": "ready",
            "generated_at": "2099-01-01T00:00:00Z",
            "latest_event": {
                "call_date": "2026-07-31",
                "metrics": {"eps_growth_pct": 0.0, "revenue_growth_pct": 12.5},
                "field_lineage": {
                    "metrics": {
                        "eps_growth_pct": "earnings_history",
                        "revenue_growth_pct": "score_overlay",
                    }
                },
            },
        }

    got = _resolve(
        "company_intelligence",
        CompanyIntelligenceAdapter(
            symbol_map_loader=lambda: {AAPL: "AAPL"},
            reader=read,
        ),
        field_ids=[
            "earnings.latest.eps_growth_pct",
            "earnings.latest.revenue_growth_pct",
        ],
        entities=[_security()],
    )
    assert calls == [{"ticker": "AAPL", "limit": 1}]
    assert [row["value"] for row in got] == [0.0, 12.5]
    assert [row["provenance"]["field_lineage"] for row in got] == [
        "earnings_history",
        "score_overlay",
    ]
    assert all(row["observed_at"] == "2026-07-31" for row in got)
    assert all(row["effective_at"] == "2026-07-31" for row in got)
    assert all(row["as_of"] == "2026-07-31" for row in got)
    assert all("2099-01-01" not in json.dumps(row) for row in got)


def test_company_intelligence_stale_context_never_emits_metric() -> None:
    got = _resolve(
        "company_intelligence",
        CompanyIntelligenceAdapter(
            symbol_map_loader=lambda: {AAPL: "AAPL"},
            reader=lambda _request: {
                "available": True,
                "status": "stale",
                "latest_event": {
                    "call_date": "2026-07-31",
                    "metrics": {"eps_growth_pct": 20.0},
                    "field_lineage": {"metrics": {"eps_growth_pct": "earnings_history"}},
                },
            },
        ),
        field_ids=["earnings.latest.eps_growth_pct"],
        entities=[_security()],
    )[0]
    assert (got["status"], got["reason_code"], got["value"]) == (
        "stale",
        "owner_stale",
        None,
    )


def _theme_adapter(calls: dict[str, int] | None = None) -> ThemeAdapter:
    counters = calls if calls is not None else {"identity": 0, "edges": 0, "meta": 0}

    def identities():
        counters["identity"] += 1
        return [
            {
                "node_id": "co:us:AAPL",
                "graph_kind": "company",
                "resolution_state": "RESOLVED",
                "security_id": AAPL,
            },
            {
                "node_id": "co:us:AAPL.THS",
                "graph_kind": "company",
                "resolution_state": "RESOLVED",
                "security_id": AAPL,
            },
            {
                "node_id": "co:us:IGNORED",
                "graph_kind": "company",
                "resolution_state": "NOT_IN_MASTER",
                "security_id": AAPL,
            },
        ]

    def edges():
        counters["edges"] += 1
        return [
            {
                "type": "MEMBER_OF",
                "src": "co:us:AAPL.THS",
                "dst": "ltheme:ths:cloud",
                "valid_from": "2026-01-01",
                "valid_to": None,
            },
            {
                "type": "MEMBER_OF",
                "src": "co:us:AAPL",
                "dst": "ltheme:finviz:ai",
                "valid_from": "2026-01-01",
                "valid_to": None,
            },
            {
                "type": "MEMBER_OF",
                "src": "co:us:AAPL",
                "dst": "ltheme:finviz:closed",
                "valid_from": "2026-01-01",
                "valid_to": "2026-08-23",
            },
            {
                "type": "MEMBER_OF",
                "src": "co:us:AAPL",
                "dst": "ltheme:finviz:future",
                "valid_from": "2026-08-24",
                "valid_to": None,
            },
            {
                "type": "EXPRESSES",
                "src": "ltheme:ths:cloud",
                "dst": "theme:ai",
                "valid_from": "2026-01-01",
                "valid_to": None,
            },
        ]

    def meta():
        counters["meta"] += 1
        return {
            "computed_at": "2026-08-23T04:00:00Z",
            "belief_time": "2026-08-23",
            "engine_version": "theme_graph.v1",
        }

    return ThemeAdapter(identity_loader=identities, edge_loader=edges, meta_loader=meta)


def test_theme_exact_sec_zero_to_many_current_direct_memberships_are_sorted() -> None:
    calls = {"identity": 0, "edges": 0, "meta": 0}
    got = _resolve(
        "theme",
        _theme_adapter(calls),
        field_ids=["theme.local.memberships"],
        entities=[_security(AAPL), _security(MSFT)],
    )
    assert calls == {"identity": 1, "edges": 1, "meta": 1}
    assert got[0]["value"] == ["ltheme:finviz:ai", "ltheme:ths:cloud"]
    assert (got[1]["status"], got[1]["reason_code"], got[1]["value"]) == (
        "unavailable",
        "owner_missing",
        None,
    )
    assert got[0]["status"] == "available"
    assert got[0]["provenance"]["relationship"] == "MEMBER_OF"
    assert got[0]["provenance"]["basis"] == "direct_source_relation"
    assert "theme:ai" not in got[0]["value"]


def test_theme_resolved_identity_with_zero_direct_edges_is_available_empty() -> None:
    adapter = ThemeAdapter(
        identity_loader=lambda: [
            {
                "node_id": "co:us:MSFT",
                "graph_kind": "company",
                "resolution_state": "RESOLVED",
                "security_id": MSFT,
            }
        ],
        edge_loader=lambda: [],
        meta_loader=lambda: {
            "computed_at": "2026-08-23T04:00:00Z",
            "belief_time": "2026-08-23",
        },
    )
    got = _resolve(
        "theme",
        adapter,
        field_ids=["theme.local.memberships"],
        entities=[_security(MSFT)],
    )[0]
    assert (got["status"], got["reason_code"], got["value"]) == (
        "available",
        None,
        [],
    )


def test_theme_subscriber_rights_are_all_or_nothing_and_dynamic() -> None:
    state = {"forbid_ths": False}
    checked: list[str] = []

    def family(node_id):
        if str(node_id).startswith("ltheme:finviz:"):
            return "finviz_themes"
        if str(node_id).startswith("ltheme:ths:"):
            return "ths_concepts"
        return None

    def assert_allowed(family_name):
        checked.append(family_name)
        if family_name == "ths_concepts" and state["forbid_ths"]:
            raise RuntimeError("rights refused")

    projector = ThemeRightsProjector(
        family_resolver=family,
        assert_allowed=assert_allowed,
    )
    adapter = _theme_adapter()
    internal = _resolve(
        "theme",
        adapter,
        field_ids=["theme.local.memberships"],
        entities=[_security()],
        audience="internal",
        rights_projector=projector,
    )[0]
    allowed = _resolve(
        "theme",
        adapter,
        field_ids=["theme.local.memberships"],
        entities=[_security()],
        audience="subscriber",
        rights_projector=projector,
    )[0]
    state["forbid_ths"] = True
    blocked = _resolve(
        "theme",
        adapter,
        field_ids=["theme.local.memberships"],
        entities=[_security()],
        audience="subscriber",
        rights_projector=projector,
    )[0]

    expected = ["ltheme:finviz:ai", "ltheme:ths:cloud"]
    assert internal["value"] == expected
    assert allowed["value"] == expected
    assert (blocked["status"], blocked["reason_code"], blocked["value"]) == (
        "rights_blocked",
        "rights_blocked",
        None,
    )
    assert checked == [
        "finviz_themes",
        "ths_concepts",
        "finviz_themes",
        "ths_concepts",
    ]
    assert "artifact_id" in internal["source"]
    assert "owner_artifact" in internal["provenance"]
    assert "artifact_id" not in allowed["source"]
    assert "owner_artifact" not in allowed["provenance"]
    assert blocked["observed_at"] == internal["observed_at"]
    assert blocked["effective_at"] == internal["effective_at"]
    assert blocked["freshness"] == internal["freshness"]
    assert blocked["quality"] == internal["quality"]


def test_theme_malformed_candidate_interval_refuses_partial_set() -> None:
    adapter = ThemeAdapter(
        identity_loader=lambda: [
            {
                "node_id": "co:us:AAPL",
                "graph_kind": "company",
                "resolution_state": "RESOLVED",
                "security_id": AAPL,
            }
        ],
        edge_loader=lambda: [
            {
                "type": "MEMBER_OF",
                "src": "co:us:AAPL",
                "dst": "ltheme:finviz:valid",
                "valid_from": "2026-01-01",
                "valid_to": None,
            },
            {
                "type": "MEMBER_OF",
                "src": "co:us:AAPL",
                "dst": "ltheme:finviz:broken",
                "valid_from": "not-a-date",
                "valid_to": None,
            },
        ],
        meta_loader=lambda: {
            "computed_at": "2026-08-23T04:00:00Z",
            "belief_time": "2026-08-23",
        },
    )
    got = _resolve(
        "theme",
        adapter,
        field_ids=["theme.local.memberships"],
        entities=[_security()],
    )[0]
    assert (got["status"], got["reason_code"], got["value"]) == (
        "unavailable",
        "owner_degraded",
        None,
    )
