from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.build_fundamental_forensics import (
    SCHEMA,
    _write_state_atomic,
    compose_state,
    detector_evaluability,
    detect_quarterly,
)


def test_atomic_private_state_gzip_is_path_independent_and_deterministic(tmp_path: Path):
    state = {
        "schema": SCHEMA,
        "generated_at": "2026-08-01T12:00:00+00:00",
        "companies": {},
    }
    first = _write_state_atomic(tmp_path / "one" / "state.json.gz", state)
    second = _write_state_atomic(tmp_path / "two" / "state.json.gz", state)

    assert first.read_bytes() == second.read_bytes()
    assert not list(tmp_path.rglob("*.tmp"))


def _q(**overrides):
    base = {
        "ticker": "TST",
        "fiscal_year": 2025,
        "fiscal_quarter": 2,
        "period_end": "2025-06-30",
        "filed": "2025-08-01",
        "revenue": 100.0,
        "gross_profit": 40.0,
        "receivables": 20.0,
        "inventory": 20.0,
        "cfo": 15.0,
        "capex": 10.0,
        "op_income": 15.0,
        "ni": 12.0,
        "contract_liabilities": 5.0,
    }
    base.update(overrides)
    return base


def test_quarterly_detectors_emit_review_prompts_without_company_score():
    prior = pd.Series(_q())
    current = pd.Series(_q(
        fiscal_year=2026,
        period_end="2026-06-30",
        filed="2026-08-01",
        revenue=105.0,
        gross_profit=36.75,  # 35% margin vs 40%
        receivables=35.0,
        inventory=40.0,
        capex=30.0,
        op_income=16.0,
    ))
    findings = detect_quarterly(current, prior, 320193)
    ids = {item["detector"] for item in findings}

    assert ids == {
        "margin_compression_despite_revenue_growth",
        "receivables_stretch",
        "inventory_build",
        "capital_intensity_rising",
    }
    encoded = json.dumps(findings).lower()
    assert '"score"' not in encoded
    assert '"rank"' not in encoded
    assert "fraud" not in encoded
    assert all(item["display_only"] for item in findings)
    assert all(item["authority"] == "review_priority_only" for item in findings)
    assert all(item["evidence"][0]["url"].startswith("https://www.sec.gov/") for item in findings)


def test_receivables_boundary_is_strictly_greater_than_ten_points():
    prior = pd.Series(_q())
    exact = pd.Series(_q(fiscal_year=2026, period_end="2026-06-30", revenue=105.0, receivables=23.0))
    # revenue +5%; receivables +15% -> exactly +10pp, therefore clear.
    assert "receivables_stretch" not in {f["detector"] for f in detect_quarterly(exact, prior, None)}


def test_coverage_uses_detector_denominators_and_consecutive_years():
    prior = pd.Series(_q(
        revenue=0.0,
        receivables=0.0,
        inventory=0.0,
        capex=0.0,
        op_income=0.0,
    ))
    current = pd.Series(_q(fiscal_year=2026, period_end="2026-06-30"))
    nonconsecutive = pd.DataFrame([
        {"fy": 2021, "period_end": "2021-12-31", "ni": 1.0, "cfo": 1.0, "assets": 10.0},
        {"fy": 2023, "period_end": "2023-12-31", "ni": 1.0, "cfo": 1.0, "assets": 10.0},
        {"fy": 2025, "period_end": "2025-12-31", "ni": 1.0, "cfo": 1.0, "assets": 10.0},
    ])

    coverage = detector_evaluability(current, prior, nonconsecutive)

    assert coverage == {
        "margin_compression_despite_revenue_growth": False,
        "receivables_stretch": False,
        "inventory_build": False,
        "capital_intensity_rising": False,
        "accruals_trending_up": False,
    }


def test_compose_state_contract_and_pit_clock(tmp_path: Path):
    q_dir = tmp_path / "data" / "edgar"
    q_dir.mkdir(parents=True)
    quarterly = pd.DataFrame([
        _q(fiscal_year=2024, period_end="2024-06-30", filed="2024-08-01"),
        _q(fiscal_year=2025, period_end="2025-06-30", filed="2025-08-01"),
        _q(
            fiscal_year=2026,
            period_end="2026-06-30",
            filed="2026-08-01",
            revenue=105.0,
            gross_profit=36.75,
            receivables=35.0,
            inventory=40.0,
            capex=30.0,
            op_income=16.0,
        ),
    ])
    quarterly.to_parquet(q_dir / "statements_quarterly.parquet", index=False)
    annual = pd.DataFrame([
        {"ticker": "TST", "fy": 2023, "period_end": "2023-12-31", "ni": 10.0, "cfo": 14.0, "assets": 100.0},
        {"ticker": "TST", "fy": 2024, "period_end": "2024-12-31", "ni": 12.0, "cfo": 13.0, "assets": 100.0},
        {"ticker": "TST", "fy": 2025, "period_end": "2025-12-31", "ni": 18.0, "cfo": 10.0, "assets": 100.0},
    ])
    annual.to_parquet(q_dir / "statements.parquet", index=False)

    state = compose_state(tmp_path, generated_at="2026-08-01T12:00:00+00:00")
    source_clock_state = compose_state(tmp_path)

    assert state["schema"] == SCHEMA
    assert state["generated_at"] == "2026-08-01T12:00:00+00:00"
    assert source_clock_state["generated_at"] == "2026-08-01T23:59:59+00:00"
    assert state["as_of"] == "2026-08-01"
    assert state["summary"]["companies"] == 1
    assert state["companies"]["TST"]["action"]["key"] == "high"
    assert len(state["companies"]["TST"]["periods"]) == 3
    encoded = json.dumps(state).lower()
    assert '"company_score"' not in encoded
    assert '"rank"' not in encoded
    assert '"fraud"' not in encoded
    assert state["source"]["basis"] == "repository quarterly and annual EDGAR panels"
