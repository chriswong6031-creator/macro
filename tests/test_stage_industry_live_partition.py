"""Wave 8 §6.2 — mixed-vintage exclusion at the industry surfaces seam.

`engine.stage_analysis._build_live_industry_surfaces` is the single seam
where LIVE per-name Stage records (current + stale + unknown, all three
buckets) get filtered down to a current-only frame before being handed to
`stage_industry.build()`, `stage_flows.build()`, and
`name_industry_percentiles()`. `prepare_live_frame()` still runs on ALL
records so every row — including stale ones — keeps its reference-taxonomy
identity for the screener's industry column; only the RANKING/AGGREGATION
frame is filtered to current tickers.

This is a NEW, narrowly-scoped test file rather than an addition to
tests/test_stage_analysis.py: that file is owned by Wave 8 PR A (the
`stage_context.v1` clock-model contract, its additive-key-set fixture pins)
and this PR must not re-edit it. `_build_live_industry_surfaces` and its call
site are the only pieces of engine/stage_analysis.py this PR (Wave 8 PR B)
owns, so the test for that seam lives here instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import stage_analysis as sa


def _rec(ticker: str, industry_id: str, industry_name: str,
        mansfield_rs: float, mansfield_rs_change: float,
        region: str = "USA") -> dict:
    return {
        "ticker": ticker, "region": region,
        "industry_id": industry_id, "industry_name": industry_name,
        "mansfield_rs": mansfield_rs, "mansfield_rs_change": mansfield_rs_change,
    }


def test_stale_ticker_excluded_from_ranks_and_flows_but_keeps_taxonomy(tmp_path: Path):
    """A stale row in the SAME industry as current rows must not distort the
    current cross-section's aggregate — but it still needs its GICS identity
    for the screener's industry column.

    Industry "10" (AAA, BBB) is a clear leader over industry "20" (CCC, DDD)
    on RS alone. SILA is a STALE row parked in industry "10" with extreme
    negative values; if it leaked into the ranking frame it would drag
    industry 10's mean RS from +19 to roughly -17, INVERTING the rank order
    (industry 20 would then out-rank industry 10) — an observable, not just
    cosmetic, defect. Correct exclusion keeps industry 10 in front.
    """
    recs = [
        _rec("AAA", "10", "Strong", 20.0, 8.0),
        _rec("BBB", "10", "Strong", 18.0, 7.0),
        _rec("CCC", "20", "Mid", 5.0, 2.0),
        _rec("DDD", "20", "Mid", 3.0, 1.0),
        # a stale row with extreme values that would visibly distort — and
        # here, INVERT — the industry-10 aggregate if it leaked into the
        # ranking frame.
        _rec("SILA", "10", "Strong", -90.0, -50.0),
    ]
    current_tickers = {"AAA", "BBB", "CCC", "DDD"}   # SILA is NOT current

    name_pct, taxonomy = sa._build_live_industry_surfaces(
        recs, root=tmp_path, asof="2026-08-20",
        current_tickers=current_tickers, target_stage_week="2026-08-14",
    )

    # Taxonomy identity is retained for EVERY ticker, including the stale one.
    assert set(taxonomy.keys()) == {"AAA", "BBB", "CCC", "DDD", "SILA"}
    assert taxonomy["SILA"]["industry_id"] == "10"

    # The stale ticker gets no current rank authority (null percentile, §6.2).
    assert "SILA" not in name_pct
    assert name_pct["AAA"] == 100.0   # AAA (rs 20) beats BBB (rs 18) within industry 10

    written = json.loads((tmp_path / "stage_analysis" / "industry_ranks.json").read_text())
    usa = written["regions"]["USA"]
    by_id = {r["industry_id"]: r for r in usa}
    assert set(by_id) == {"10", "20"}
    assert by_id["10"]["n"] == 2         # AAA + BBB only — SILA never entered the group
    assert by_id["20"]["n"] == 2
    # Industry 10 (real RS ~19) correctly out-ranks industry 20 (real RS ~4).
    # Had SILA leaked in, industry 10's mean would have inverted to ~-17 and
    # industry 20 would have ranked first instead.
    assert by_id["10"]["rank"] == 1
    assert by_id["20"]["rank"] == 2


def test_no_current_tickers_yields_empty_ranks_with_full_taxonomy(tmp_path: Path):
    """§2.4 — no target week resolved means `current_tickers` is empty/None:
    no current cross-sectional authority, but taxonomy identity is still
    joined for every row (it feeds the screener regardless of currentness)."""
    recs = [_rec("AAA", "10", "Strong", 20.0, 8.0)]

    name_pct, taxonomy = sa._build_live_industry_surfaces(
        recs, root=tmp_path, asof="2026-08-20",
        current_tickers=None, target_stage_week=None,
    )

    assert taxonomy.get("AAA") is not None
    assert taxonomy["AAA"]["industry_id"] == "10"
    assert name_pct == {}

    written = json.loads((tmp_path / "stage_analysis" / "industry_ranks.json").read_text())
    assert written["n_industries"] == 0
    assert written["regions"] == {}


def test_current_tickers_across_regions_isolated_per_region(tmp_path: Path):
    """A stale row in one region must not contaminate a DIFFERENT region's
    current cross-section either."""
    recs = [
        _rec("AAA", "10", "Strong", 20.0, 8.0, region="USA"),
        _rec("BBB", "10", "Strong", 18.0, 7.0, region="USA"),
        _rec("STALE_EU", "40", "EuroOne", -99.0, -99.0, region="EUROPE"),
    ]
    current_tickers = {"AAA", "BBB"}   # STALE_EU excluded

    name_pct, taxonomy = sa._build_live_industry_surfaces(
        recs, root=tmp_path, asof="2026-08-20",
        current_tickers=current_tickers, target_stage_week="2026-08-14",
    )
    assert "STALE_EU" not in name_pct

    written = json.loads((tmp_path / "stage_analysis" / "industry_ranks.json").read_text())
    assert "EUROPE" not in written["regions"]  # the only EU row was excluded
    assert "USA" in written["regions"]
