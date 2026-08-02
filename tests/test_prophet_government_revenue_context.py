"""Authority-boundary tests for Government Revenue -> Prophet annotations."""
from __future__ import annotations

import json
from pathlib import Path

from engine import prophet_bridge as pb


def _buy(ticker: str, score: int, spot: float) -> dict:
    return {
        "ticker": ticker,
        "dir": "up",
        "conviction": {
            "score": score,
            "band": "neutral",
            "drivers": ["momentum"],
            "cautions": [],
        },
        "entry_signal": {
            "act_level": 3,
            "spot": spot,
            "chase_above": spot + 1,
            "atr_pct": 2.0,
        },
        "hold": {"anchor": "2026-07-31", "invalidation": spot - 8},
    }


def _write_standouts(root: Path) -> Path:
    path = root / "site" / "factordata" / "us_standouts.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "as_of": "2026-07-31",
            "gate_go": True,
            "buy": [_buy("LMT", 82, 500.0), _buy("NOC", 75, 610.0)],
        }),
        encoding="utf-8",
    )
    return path


def _artifact_freshness(
    *,
    status: str = "ok",
    opportunity_status: str = "ok",
    award_event_status: str = "ok",
    observed_at: str = "2026-08-01T23:00:00Z",
) -> dict:
    return {
        "status": status,
        "aggregate": {
            "status": "ok",
            "known_at": observed_at,
            "freshness_sla_days": 35,
        },
        "award_detail": {
            "status": "ok",
            "observed_at": observed_at,
            "freshness_sla_days": 4,
        },
        "actions": {
            "status": "ok",
            "observed_at": observed_at,
            "freshness_sla_days": 4,
        },
        "opportunities": {
            "status": opportunity_status,
            "observed_at": observed_at,
            "freshness_sla_minutes": 90,
        },
        "award_events": {
            "status": award_event_status,
            "observed_at": observed_at,
            "freshness_sla_days": 4,
            "bounded_sample_complete": True,
            "source_exhausted": False,
            "truncated_by_safety_cap": True,
            "coverage_manifest_id": "award-coverage-" + "a" * 64,
            "coverage_manifest": {"schema_version": "test", "entities": []},
        },
    }


def _context() -> dict:
    return {
        "as_of": "2026-07-31",
        "known_at": "2026-08-01T08:00:00Z",
        "freshness": {"status": "ok", "opportunities": "ok"},
        "metrics": {
            "award_velocity_yoy_pct": 14.25,
            "latest_complete_month": "2026-05",
            "funded_backlog": 12_500_000_000,
        },
        "recompete_candidates": [],
        "opportunity_candidates": [{
            "notice_id": "opp-1",
            "title": "Hypersonic interceptor sustainment",
            "days_to_response": 17,
            "known_at": "2026-08-01T07:00:00Z",
            "source_url": "https://sam.gov/opp/opp-1/view",
            "match": {
                "evidence_class": "rule_based_exposure_candidate",
                "label_limit": "not a bidder probability, award forecast, or revenue estimate",
            },
        }],
        "catalyst_facts": [],
        "confidence": "high",
        "provenance": [{"source": "USAspending"}],
        "allowed_behavior": "annotate_only",
        "authority": {
            "can_add_candidates": False,
            "can_rank": False,
            "can_size": False,
            "can_gate": False,
            "can_escalate": False,
        },
    }


def test_loader_projects_official_context_without_authority(tmp_path: Path) -> None:
    standouts_path = _write_standouts(tmp_path)
    artifact = tmp_path / "data" / "government_revenue" / "latest.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps({
            "schema_version": "company_government_revenue.v1",
            "as_of": "2026-07-31",
            "known_at": "2026-08-01T23:00:00Z",
            "freshness": _artifact_freshness(),
            "companies": [{
                "ticker": "lmt",
                "metrics": {
                    "award_velocity_yoy_pct": 14.25,
                    "latest_complete_month": "2026-05",
                    "unknown_score": 99,
                },
                "catalyst_facts": [{"label": "F-35 modification"}],
                "opportunity_candidates": [{
                    "notice_id": "opp-1",
                    "title": "Hypersonic interceptor sustainment",
                    "days_to_response": 17,
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

    assert pb._load_government_revenue_context(standouts_path, "2026-07-31") == {}
    result = pb._load_government_revenue_context(standouts_path, "2026-08-01")

    assert set(result) == {"LMT"}
    assert result["LMT"]["metrics"]["award_velocity_yoy_pct"] == 14.25
    assert "unknown_score" not in result["LMT"]["metrics"]
    assert result["LMT"]["allowed_behavior"] == "annotate_only"
    assert result["LMT"]["opportunity_candidates"][0]["notice_id"] == "opp-1"
    assert not any(result["LMT"]["authority"].values())


def test_loader_federates_only_receipt_bound_reviewed_award_changes(tmp_path: Path) -> None:
    standouts_path = _write_standouts(tmp_path)
    artifact = tmp_path / "data" / "government_revenue" / "latest.json"
    artifact.parent.mkdir(parents=True)

    def event(event_id: str, *, mapping: str, known_at: str) -> dict:
        reviewed = mapping == "reviewed"
        return {
            "contract": "government_procurement_event.v2",
            "event_id": event_id,
            "kind": "award_change",
            "title_original": "New obligation observed — FA1234",
            "change": {
                "type": "obligation",
                "known_at": known_at,
                "effective_at": "2026-08-01T12:00:00Z",
            },
            "award_change": {
                "award_key": "CONT_AWD_001",
                "piid": "FA1234",
                "action_id": "action-0001",
                "recipient_name": "Acme Defense Systems",
                "event_type": "obligation",
                "source_rail": "usaspending_award_action",
            },
            "amounts": [{"id": "federal_action_obligation", "value": 12_500_000}],
            "primary_amount_id": "federal_action_obligation",
            "listed_company_impacts": ([{
                "ticker": "LMT",
                "relation_semantic": "reviewed",
                "resolution_state": "confirmed",
                "confidence": "high",
                "materiality": {"band": "low"},
                "evidence_refs": ["recipient:UEI123", "ownership:edge-1"],
                "ownership_path": [{"from": "UEI123", "to": "LMT"}],
            }] if reviewed else []),
            "evidence": {
                "mapping_class": mapping,
                "receipts": [{"ref_id": "receipt-1"}],
            },
            "authority": {
                "tier": "display",
                "context_only": True,
                "can_rank": False,
                "can_size": False,
                "can_gate": False,
                "can_originate_signal": False,
                "can_add_candidates": False,
                "can_escalate": False,
            },
        }

    artifact.write_text(
        json.dumps({
            "schema_version": "company_government_revenue.v1",
            "as_of": "2026-08-01",
            "known_at": "2026-08-01T23:00:00Z",
            "freshness": _artifact_freshness(),
            "companies": [{"ticker": "LMT", "metrics": {"award_velocity_yoy_pct": 4.0}}],
            "procurement_workspace": {
                "schema_version": "government_procurement_workspace.v2",
                "events": [
                    event("reviewed", mapping="reviewed", known_at="2026-08-01T20:00:00Z"),
                    event("unmapped", mapping="unmapped", known_at="2026-08-01T19:00:00Z"),
                    event("future", mapping="reviewed", known_at="2026-08-02T01:00:00Z"),
                ],
            },
        }),
        encoding="utf-8",
    )

    context = pb._load_government_revenue_context(standouts_path, "2026-08-01")["LMT"]

    assert [row["event_id"] for row in context["award_change_events"]] == ["reviewed"]
    assert context["award_change_events"][0]["issuer_link"]["relation_semantic"] == "reviewed"
    assert context["award_change_events"][0]["allowed_behavior"] == "annotate_only"
    sentence = pb._government_revenue_sentence(context)
    assert sentence is not None
    assert "USAspending recorded obligation" in sentence[0]
    assert "not recognized revenue" in sentence[0]

    payload = json.loads(artifact.read_text())
    payload["freshness"]["award_events"]["status"] = "partial"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    degraded = pb._load_government_revenue_context(standouts_path, "2026-08-01")["LMT"]
    assert degraded["award_change_events"] == []

    payload["freshness"]["award_events"]["status"] = "ok"
    for malformed_authority in (
        {},
        {
            "tier": "display",
            "context_only": True,
            "can_rank": 1,
            "can_size": False,
            "can_gate": False,
            "can_originate_signal": False,
            "can_add_candidates": False,
            "can_escalate": False,
        },
    ):
        payload["procurement_workspace"]["events"][0]["authority"] = malformed_authority
        artifact.write_text(json.dumps(payload), encoding="utf-8")
        context = pb._load_government_revenue_context(
            standouts_path, "2026-08-01"
        )["LMT"]
        assert context["award_change_events"] == []


def test_loader_fails_closed_when_overall_procurement_freshness_is_degraded(
    tmp_path: Path,
) -> None:
    standouts_path = _write_standouts(tmp_path)
    artifact = tmp_path / "data" / "government_revenue" / "latest.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps({
            "schema_version": "company_government_revenue.v1",
            "as_of": "2026-07-31",
            "known_at": "2026-08-01T23:00:00Z",
            "freshness": _artifact_freshness(
                status="partial", opportunity_status="partial"
            ),
            "companies": [{
                "ticker": "LMT",
                "metrics": {"award_velocity_yoy_pct": 99.0},
                "catalyst_facts": [{"label": "must not reach prose"}],
            }],
        }),
        encoding="utf-8",
    )

    assert pb._load_government_revenue_context(standouts_path, "2026-08-01") == {}


def test_loader_suppresses_stale_opportunities_but_keeps_fresh_awards(
    tmp_path: Path,
) -> None:
    standouts_path = _write_standouts(tmp_path)
    artifact = tmp_path / "data" / "government_revenue" / "latest.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps({
            "schema_version": "company_government_revenue.v1",
            "as_of": "2026-07-31",
            "known_at": "2026-08-01T23:00:00Z",
            "freshness": _artifact_freshness(opportunity_status="stale"),
            "companies": [{
                "ticker": "LMT",
                "metrics": {"award_velocity_yoy_pct": 14.25},
                "opportunity_candidates": [{"notice_id": "stale-opp"}],
            }],
        }),
        encoding="utf-8",
    )

    context = pb._load_government_revenue_context(standouts_path, "2026-08-01")

    assert context["LMT"]["metrics"]["award_velocity_yoy_pct"] == 14.25
    assert context["LMT"]["freshness"]["opportunities"] == "stale"
    assert context["LMT"]["opportunity_candidates"] == []


def test_loader_recomputes_elapsed_sla_before_prophet_annotation(tmp_path: Path) -> None:
    standouts_path = _write_standouts(tmp_path)
    artifact = tmp_path / "data" / "government_revenue" / "latest.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps({
            "schema_version": "company_government_revenue.v1",
            "as_of": "2026-07-31",
            "known_at": "2026-08-01T08:00:00Z",
            "freshness": _artifact_freshness(),
            "companies": [{
                "ticker": "LMT",
                "metrics": {"award_velocity_yoy_pct": 14.25},
                "opportunity_candidates": [{"notice_id": "expired-opp"}],
            }],
        }),
        encoding="utf-8",
    )

    assert pb._load_government_revenue_context(standouts_path, "2026-08-10") == {}


def test_context_cannot_change_prophet_selection_or_plan_math(
    tmp_path: Path, monkeypatch,
) -> None:
    standouts_path = _write_standouts(tmp_path)
    monkeypatch.setattr(pb, "_load_stage_tilt_inputs", lambda: None)
    monkeypatch.setattr(pb, "_load_price_history", lambda _ticker: None)
    monkeypatch.setattr(pb, "resolve_option", lambda **_kwargs: None)

    monkeypatch.setattr(pb, "_load_government_revenue_context", lambda _path, _asof=None: {})
    baseline = pb.originate_plans(
        standouts_path, "2026-08-01", existing_ids=set(), thetadata_store=None
    )

    monkeypatch.setattr(
        pb,
        "_load_government_revenue_context",
        lambda _path, _asof=None: {"LMT": _context()},
    )
    enriched = pb.originate_plans(
        standouts_path, "2026-08-01", existing_ids=set(), thetadata_store=None
    )

    invariant_fields = (
        "id", "asset", "direction", "trigger", "entry", "invalidation",
        "targets", "horizon_days", "min_hold_days", "tranche",
        "option_contract", "stage_tilt", "_conviction_score", "_act_level",
        "_r_unit", "_gate_go",
    )
    assert [plan["id"] for plan in baseline] == [plan["id"] for plan in enriched]
    for base_plan, enriched_plan in zip(baseline, enriched, strict=True):
        assert {key: base_plan[key] for key in invariant_fields} == {
            key: enriched_plan[key] for key in invariant_fields
        }

    base_lmt = next(plan for plan in baseline if plan["asset"] == "LMT")
    enriched_lmt = next(plan for plan in enriched if plan["asset"] == "LMT")
    enriched_noc = next(plan for plan in enriched if plan["asset"] == "NOC")
    assert "government_revenue_context" not in base_lmt
    assert enriched_lmt["government_revenue_context"]["allowed_behavior"] == "annotate_only"
    assert enriched_lmt["context_engines"] == ["government_revenue_foresight"]
    assert "Government-revenue context" in enriched_lmt["thesis"]
    assert "not a bidder or award forecast" in enriched_lmt["thesis"]
    assert "政府收入背景" in enriched_lmt["thesis_zh"]
    assert "government_revenue_context" not in enriched_noc
