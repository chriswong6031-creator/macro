from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from scripts.build_fundamental_forensics import (
    PUBLIC_SUMMARY_MAX_AGE_DAYS,
    PUBLIC_SUMMARY_RELATIVE,
    PUBLIC_SUMMARY_SCHEMA as SCHEMA_PUBLIC,
    SCHEMA,
    _write_public_summary,
    _write_state_atomic,
    compose_state,
    detector_evaluability,
    detect_quarterly,
    public_summary_projection,
    read_public_summary,
    render_shell,
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


def _render_into(tmp_path: Path, root: Path, *, summary=None) -> str:
    """Render the shell inside tmp_path against the real templates."""
    (tmp_path / "templates").symlink_to(root / "templates")
    if summary is not None:
        _write_public_summary(tmp_path, summary)
    return render_shell(tmp_path, state_summary=summary).read_text(encoding="utf-8")


def test_public_summary_projection_emits_only_the_two_free_counts():
    """A count names nobody; anything that could name somebody must not survive."""
    projected = public_summary_projection({
        "companies": 1240,
        "findings": 3417,
        "high": 88,
        "latest_filing": "2026-08-05",
        "detector_coverage": {"accrual": 12},
        "top_symbol": "SMCI",
        "companies_list": ["AAPL", "SMCI"],
    })
    assert projected == {"companies": 1240, "findings": 3417}


def test_anonymous_preview_omits_the_count_fact_when_no_summary_exists(tmp_path: Path):
    """A fresh clone, a CI checkout and the first build all lack the projection."""
    html = _render_into(tmp_path, Path(__file__).resolve().parents[1])
    assert 'class="ff-gate-facts"' in html
    assert "Last pass" not in html
    assert "companies read" not in html
    # The absent fact must be omitted whole, never printed as a zero.
    assert "0 companies read" not in html


def test_anonymous_preview_prints_counts_supplied_by_the_build(tmp_path: Path):
    html = _render_into(tmp_path, Path(__file__).resolve().parents[1], summary={"companies": 1240, "findings": 3417})
    assert "1,240 companies read, 3,417 changes ranked for a look" in html
    assert "读取 1,240 家公司，排出 3,417 项值得一看的变化" in html


def test_build_site_compat_hook_prints_the_same_counts_as_the_forensics_build(tmp_path: Path):
    """render_from_state() re-renders this shell moments after the nightly
    forensics build (daily.yml: forensics, then build_site) and again on every
    render.yml lane that never composes state. A count carried only in-process
    would be erased there within seconds and would never exist on a render-lane
    rebuild, so the fact has to survive a render that is handed no summary."""
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "templates").symlink_to(root / "templates")
    _write_public_summary(tmp_path, {"companies": 1240, "findings": 3417, "top_symbol": "SMCI"})

    html = render_shell(tmp_path).read_text(encoding="utf-8")  # no state_summary — the compat-hook path

    assert "1,240 companies read, 3,417 changes ranked for a look" in html
    assert "SMCI" not in html


def test_unreadable_or_foreign_public_summary_degrades_to_no_fact(tmp_path: Path):
    path = tmp_path / PUBLIC_SUMMARY_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    unusable = (
        "{ not json",
        json.dumps({"companies": 5, "findings": 5}),           # no schema
        json.dumps({"schema": "other/v9"}),                     # foreign schema
        json.dumps({"schema": SCHEMA_PUBLIC, "companies": 5, "findings": 5}),  # unstamped
    )
    for payload in unusable:
        path.write_text(payload, encoding="utf-8")
        assert read_public_summary(tmp_path) == {}
    assert read_public_summary(tmp_path / "nowhere") == {}


def test_public_summary_stops_being_published_once_it_outlives_its_build(tmp_path: Path):
    """daily.yml's run_py annotates a failed builder but does NOT exit non-zero,
    so a broken forensics build leaves the nightly green while build_site keeps
    re-rendering this page from the last good file. Without a bound the counts
    would freeze and stay published forever — the exact stale-stat defect the
    preview shipped without totals to avoid."""
    built = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _write_public_summary(tmp_path, {"companies": 1240, "findings": 3417}, generated_at=built.isoformat())

    fresh = built + timedelta(days=PUBLIC_SUMMARY_MAX_AGE_DAYS)
    assert read_public_summary(tmp_path, now=fresh) == {"companies": 1240, "findings": 3417}

    stale = built + timedelta(days=PUBLIC_SUMMARY_MAX_AGE_DAYS + 1)
    assert read_public_summary(tmp_path, now=stale) == {}

    # ...and the page omits the fact whole rather than printing frozen counts.
    (tmp_path / "templates").symlink_to(Path(__file__).resolve().parents[1] / "templates")
    import scripts.build_fundamental_forensics as bff
    real_read = bff.read_public_summary
    try:
        bff.read_public_summary = lambda root, **kw: real_read(root, now=stale)
        html = bff.render_shell(tmp_path).read_text(encoding="utf-8")
    finally:
        bff.read_public_summary = real_read
    assert "companies read" not in html
    assert "1,240" not in html
