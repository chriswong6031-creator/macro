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


def _context() -> dict:
    return {
        "as_of": "2026-07-31",
        "known_at": "2026-08-01T08:00:00Z",
        "metrics": {
            "award_velocity_yoy_pct": 14.25,
            "latest_complete_month": "2026-05",
            "funded_backlog": 12_500_000_000,
        },
        "recompete_candidates": [],
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
            "known_at": "2026-08-01T08:00:00Z",
            "companies": [{
                "ticker": "lmt",
                "metrics": {
                    "award_velocity_yoy_pct": 14.25,
                    "latest_complete_month": "2026-05",
                    "unknown_score": 99,
                },
                "catalyst_facts": [{"label": "F-35 modification"}],
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
    assert not any(result["LMT"]["authority"].values())


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
    assert "政府收入背景" in enriched_lmt["thesis_zh"]
    assert "government_revenue_context" not in enriched_noc
