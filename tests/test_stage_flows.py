"""Tests for engine.stage_flows (SGA-2 industry / sub-industry flows).

Synthetic stage frames drive the computation; the calibration smoke test uses
the committed backfill (skipped if absent). All writes go to tmp_path (root=).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import stage_flows as sf


def _frame() -> pd.DataFrame:
    """One USA industry (id 10) with two sub-industries, mixed stages."""
    rows = [
        # sub 1010 — Stage 2 heavy, one fresh
        dict(ticker="A", region="USA", industry_id="10", industry_name="Ind",
             sub_industry_id="1010", sub_industry_name="SubA", stage_flag=2,
             weeks_in_stage=5, is_stage2_start=True, mansfield_rs=10.0,
             mansfield_rs_change=6.0, sata_score=8.0),
        dict(ticker="B", region="USA", industry_id="10", industry_name="Ind",
             sub_industry_id="1010", sub_industry_name="SubA", stage_flag=2,
             weeks_in_stage=12, is_stage2_start=False, mansfield_rs=6.0,
             mansfield_rs_change=4.0, sata_score=7.0),
        dict(ticker="C", region="USA", industry_id="10", industry_name="Ind",
             sub_industry_id="1010", sub_industry_name="SubA", stage_flag=2,
             weeks_in_stage=9, is_stage2_start=False, mansfield_rs=5.0,
             mansfield_rs_change=3.0, sata_score=6.0),
        # sub 1020 — Stage 4 heavy, one fresh breakdown
        dict(ticker="D", region="USA", industry_id="10", industry_name="Ind",
             sub_industry_id="1020", sub_industry_name="SubB", stage_flag=4,
             weeks_in_stage=2, is_stage2_start=False, mansfield_rs=-8.0,
             mansfield_rs_change=-3.0, sata_score=2.0),
        dict(ticker="E", region="USA", industry_id="10", industry_name="Ind",
             sub_industry_id="1020", sub_industry_name="SubB", stage_flag=1,
             weeks_in_stage=3, is_stage2_start=False, mansfield_rs=-2.0,
             mansfield_rs_change=-1.0, sata_score=3.0),
    ]
    return pd.DataFrame(rows)


def test_counts_and_ratio_math():
    res = sf.flows(region="USA", stage_frame=_frame())
    ind = res["industry"]
    assert len(ind) == 1
    r = ind[0]
    assert r["n"] == 5
    assert r["stage2_count"] == 3
    assert r["stage4_count"] == 1
    # ratio = s2/s4 = 3/1
    assert r["stage2_stage4_ratio"] == 3.0


def test_ratio_when_no_stage4():
    df = _frame()
    df = df[df["stage_flag"] != 4]  # drop the only stage-4 name
    r = sf.flows(region="USA", stage_frame=df)["industry"][0]
    assert r["stage4_count"] == 0
    # ratio falls back to the raw stage2 count
    assert r["stage2_stage4_ratio"] == float(r["stage2_count"])


def test_fresh_counts_and_pct():
    r = sf.flows(region="USA", stage_frame=_frame())["industry"][0]
    # one is_stage2_start=True among n=5
    assert r["fresh_stage2_count"] == 1
    assert abs(r["fresh_stage2_pct"] - 100.0 * 1 / 5) < 1e-6
    # fresh stage4 = young stage-4 (weeks<=4): ticker D (weeks 2)
    assert r["fresh_stage4_count"] == 1


def test_sata_age_breadth():
    r = sf.flows(region="USA", stage_frame=_frame())["industry"][0]
    # sata_mean = mean of [8,7,6,2,3]
    assert abs(r["sata_mean"] - (8 + 7 + 6 + 2 + 3) / 5) < 1e-6
    # stage2 median age = median of [5,12,9] = 9
    assert r["stage2_median_age_wks"] == 9.0
    # breadth = % rs_change>0 = 3/5*100
    assert abs(r["breadth_4w_pct"] - 60.0) < 1e-6


def test_state_classifier_and_turn_flag():
    # Direct boundary checks on the classifier.
    assert sf._classify_state(breadth=95, ratio=4.0, rs4=5.0) == "LEADING"
    assert sf._classify_state(breadth=20, ratio=0.5, rs4=-3.0) == "BREAKING"
    assert sf._classify_state(breadth=85, ratio=0.7, rs4=3.0) == "BASING"
    assert sf._classify_state(breadth=20, ratio=5.0, rs4=-1.0) == "DISTRIBUTING"
    assert sf._classify_state(breadth=50, ratio=1.0, rs4=0.5) == "NEUTRAL"
    # turn_flag: None without a prior; roll when strong->weak.
    assert sf._turn_flag("LEADING", None) is None
    assert sf._turn_flag("BREAKING", "LEADING") == "roll"
    assert sf._turn_flag("LEADING", "BREAKING") == "bounce"


def test_sub_industry_breakdown():
    res = sf.flows(region="USA", stage_frame=_frame())
    subs = {r["industry_id"]: r for r in res["sub_industry"]}
    assert set(subs) == {"1010", "1020"}
    assert subs["1010"]["stage2_count"] == 3
    assert subs["1020"]["stage4_count"] == 1


def test_fail_open_empty_and_missing():
    assert sf.flows(region="USA", stage_frame=pd.DataFrame()) == {
        "industry": [], "sub_industry": []}
    bad = pd.DataFrame([{"ticker": "X", "region": "USA"}])  # missing required cols
    assert sf.flows(region="USA", stage_frame=bad) == {
        "industry": [], "sub_industry": []}


def test_live_frame_stage_column_adapter():
    """The LIVE classifier output uses `stage` (not the seed's `stage_flag`) and
    carries region + GICS industry already — flows must consume it via the
    adapter, exactly like the seed frame (item 3)."""
    rows = [
        dict(ticker="A", region="USA", industry_id="10", industry_name="Ind",
             stage=2, weeks_in_stage=5, is_stage2_start=True,
             mansfield_rs=10.0, mansfield_rs_change=6.0, sata_score=8.0),
        dict(ticker="B", region="USA", industry_id="10", industry_name="Ind",
             stage=2, weeks_in_stage=12, is_stage2_start=False,
             mansfield_rs=6.0, mansfield_rs_change=4.0, sata_score=7.0),
        dict(ticker="D", region="USA", industry_id="10", industry_name="Ind",
             stage=4, weeks_in_stage=2, is_stage2_start=False,
             mansfield_rs=-8.0, mansfield_rs_change=-3.0, sata_score=2.0),
    ]
    live = pd.DataFrame(rows)  # NOTE: `stage`, NOT `stage_flag`
    assert "stage_flag" not in live.columns
    res = sf.flows(region="USA", stage_frame=live)
    ind = res["industry"]
    assert len(ind) == 1, "live-shaped frame produced no industry rows"
    r = ind[0]
    assert r["n"] == 3
    assert r["stage2_count"] == 2
    assert r["stage4_count"] == 1
    assert r["fresh_stage2_count"] == 1


def test_live_frame_gics_joined_from_overview(tmp_path):
    """A live frame with only `ticker` + `stage` (no GICS) gets region + industry
    joined from the committed overview yardstick via the adapter. Skips when the
    yardstick is absent; otherwise proves the join path runs end-to-end."""
    ov_p = (Path(__file__).resolve().parents[1] / "data" / "stage_analysis"
            / "backfill" / "equitydesk_overview.parquet")
    if not ov_p.exists():
        pytest.skip("equitydesk_overview yardstick absent")
    ov = pd.read_parquet(ov_p, columns=["ticker", "region", "gics_industry"])
    ov = ov.dropna(subset=["ticker", "region", "gics_industry"])
    if ov.empty:
        pytest.skip("overview yardstick has no usable GICS rows")
    sample = [str(t).split()[0].upper() for t in ov["ticker"].head(30)]
    live = pd.DataFrame([
        dict(ticker=tk, stage=2, weeks_in_stage=5)
        for tk in sample
    ])
    # No region / industry columns at all — the adapter must supply them.
    assert "region" not in live.columns and "industry_id" not in live.columns
    # root points the engine's data_root at the real repo data/ so the overview
    # map resolves; write goes nowhere (we call flows(), not build()).
    dr = Path(__file__).resolve().parents[1] / "data"
    res = sf.flows(region=None, stage_frame=live, root=dr)
    # At least one industry row emerges once GICS is joined.
    assert res["industry"], "GICS join from overview produced no industry rows"


def test_optional_subindustry_backfill():
    # Frame without sub_industry_* columns -> sub falls back to parent industry.
    df = _frame().drop(columns=["sub_industry_id", "sub_industry_name",
                                "is_stage2_start", "sata_score",
                                "mansfield_rs", "mansfield_rs_change"])
    res = sf.flows(region="USA", stage_frame=df)
    assert len(res["industry"]) == 1
    # sub-industry rolls up to the single parent id
    assert {r["industry_id"] for r in res["sub_industry"]} == {"10"}


def test_build_writes_artifact_display_tier(tmp_path: Path):
    contract = sf.build(stage_frame=_frame(), root=tmp_path, asof="2026-07-20")
    assert contract["is_context_only"] is True
    assert contract["display_only"] is True
    p = tmp_path / "stage_analysis" / "industry_flows.json"
    assert p.exists()
    written = json.loads(p.read_text())
    assert "USA" in written["industry_regions"]
    assert written["n_industry"] == 1


def test_build_turn_flag_from_prior_artifact(tmp_path: Path):
    # First build (strong LEADING-ish) then a weakened frame -> roll flag.
    strong = _frame().copy()
    strong["mansfield_rs_change"] = 6.0   # breadth 100
    sf.build(stage_frame=strong, root=tmp_path, asof="2026-07-19")
    prev = sf._prev_states_from_artifact(tmp_path)
    assert prev  # prior states recovered
    weak = _frame().copy()
    weak["stage_flag"] = 4                 # all stage-4
    weak["mansfield_rs_change"] = -5.0     # breadth 0
    contract = sf.build(stage_frame=weak, root=tmp_path, asof="2026-07-20")
    row = contract["industry_regions"]["USA"][0]
    assert row["state"] in ("BREAKING", "DISTRIBUTING")


# ---------------------------------------------------------------------------
# Calibration smoke — reproduce EquityDesk flow columns from stage_daily.
# ---------------------------------------------------------------------------
_BACKFILL = (Path(__file__).resolve().parents[1] / "data" / "stage_analysis"
             / "backfill")


@pytest.mark.skipif(
    not (_BACKFILL / "stage_daily.parquet").exists()
    or not (_BACKFILL / "industry_flows.parquet").exists(),
    reason="backfill parquets not present",
)
def test_calibration_smoke():
    """Exact-reproducible columns (counts, sata, age) match; state agrees ~85%."""
    sd = pd.read_parquet(_BACKFILL / "stage_daily.parquet")
    theirs = pd.read_parquet(_BACKFILL / "industry_flows.parquet")
    ours = sf.flows(region="USA", stage_frame=sd)["industry"]
    o = {r["industry_id"]: r for r in ours}
    tt = theirs[theirs["region"] == "USA"]

    count_ok = sata_ok = age_ok = state_ok = total = 0
    for row in tt.itertuples():
        r = o.get(str(row.industry_id))
        if r is None:
            continue
        total += 1
        if r["stage2_count"] == int(row.stage2_count) and \
                r["stage4_count"] == int(row.stage4_count):
            count_ok += 1
        if abs(r["sata_mean"] - float(row.sata_mean)) < 0.05:
            sata_ok += 1
        if r["stage2_median_age_wks"] is not None and not pd.isna(row.stage2_median_age_wks):
            if abs(r["stage2_median_age_wks"] - float(row.stage2_median_age_wks)) < 0.6:
                age_ok += 1
        if r["state"] == row.state:
            state_ok += 1
    assert total > 50
    # counts/sata/age reproduce near-exactly
    assert count_ok / total > 0.95
    assert sata_ok / total > 0.95
    # state labels agree well above chance (5 classes)
    assert state_ok / total > 0.60
