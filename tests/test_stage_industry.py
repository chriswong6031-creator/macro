"""Tests for engine.stage_industry (SGA-2 industry ranks).

Synthetic stage frames drive the computation; the calibration smoke test uses
the committed backfill (skipped if absent). All writes go to tmp_path (root=)
so the MM_DATA_GUARD tripwire never sees the real data/ tree.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import stage_industry as si


def _frame() -> pd.DataFrame:
    """Two regions, three industries; RS/RS-change monotone so ranks are known."""
    rows = [
        # USA — industry 10 (strong), 20 (mid), 30 (weak)
        dict(ticker="A", region="USA", industry_id="10", industry_name="Strong",
             mansfield_rs=20.0, mansfield_rs_change=8.0),
        dict(ticker="B", region="USA", industry_id="10", industry_name="Strong",
             mansfield_rs=18.0, mansfield_rs_change=7.0),
        dict(ticker="C", region="USA", industry_id="20", industry_name="Mid",
             mansfield_rs=2.0, mansfield_rs_change=1.0),
        dict(ticker="D", region="USA", industry_id="20", industry_name="Mid",
             mansfield_rs=0.0, mansfield_rs_change=0.0),
        dict(ticker="E", region="USA", industry_id="30", industry_name="Weak",
             mansfield_rs=-15.0, mansfield_rs_change=-6.0),
        dict(ticker="F", region="USA", industry_id="30", industry_name="Weak",
             mansfield_rs=-12.0, mansfield_rs_change=-5.0),
        # EUROPE — one industry (isolation test)
        dict(ticker="G", region="EUROPE", industry_id="40", industry_name="EuroOne",
             mansfield_rs=5.0, mansfield_rs_change=2.0),
    ]
    return pd.DataFrame(rows)


def test_ranks_ordering_and_score():
    out = si.ranks(region="USA", stage_frame=_frame())
    assert len(out) == 3
    by_id = {r["industry_id"]: r for r in out}
    # Strong industry ranks 1, weak ranks last.
    assert by_id["10"]["rank"] == 1
    assert by_id["30"]["rank"] == 3
    # score is monotone with strength
    assert by_id["10"]["score"] > by_id["20"]["score"] > by_id["30"]["score"]
    # score = W_RSROC*z_rsroc + W_MOM*z_mom
    r = by_id["10"]
    exp = si.W_RSROC * r["z_rsroc"] + si.W_MOM * r["z_mom"]
    # z's and score are independently rounded to 4dp, so allow rounding drift.
    assert abs(r["score"] - exp) < 1e-3


def test_percentile_and_bucket():
    out = si.ranks(region="USA", stage_frame=_frame())
    by_id = {r["industry_id"]: r for r in out}
    # top rank -> 100, bottom rank -> 0 (100*(n-rank)/(n-1))
    assert by_id["10"]["industry_percentile"] == 100.0
    assert by_id["30"]["industry_percentile"] == 0.0
    # rank-1 of any region is Leading.
    assert by_id["10"]["bucket"] == "Leading"


def test_bucket_quartiles_clean():
    """Four industries -> one per quartile bucket, top to bottom."""
    rows = []
    for i, (iid, rs) in enumerate([("A", 20.0), ("B", 8.0), ("C", -2.0), ("D", -20.0)]):
        rows.append(dict(ticker=f"t{i}", region="USA", industry_id=iid,
                         industry_name=iid, mansfield_rs=rs, mansfield_rs_change=rs))
    out = si.ranks(region="USA", stage_frame=pd.DataFrame(rows))
    by_id = {r["industry_id"]: r for r in out}
    assert by_id["A"]["bucket"] == "Leading"
    assert by_id["B"]["bucket"] == "Improving"
    assert by_id["C"]["bucket"] == "Weakening"
    assert by_id["D"]["bucket"] == "Lagging"


def test_all_regions_and_isolation():
    out = si.ranks(region=None, stage_frame=_frame())
    regions = {r["region"] for r in out}
    assert regions == {"USA", "EUROPE"}
    # EUROPE single industry -> percentile 100, rank 1, its own z's are 0
    euro = [r for r in out if r["region"] == "EUROPE"][0]
    assert euro["rank"] == 1
    assert euro["industry_percentile"] == 100.0
    assert euro["z_rsroc"] == 0.0 and euro["z_mom"] == 0.0


def test_name_industry_percentiles():
    pct = si.name_industry_percentiles(stage_frame=_frame())
    # Within USA industry 10: A (rs 20) > B (rs 18) -> A=100, B=0
    assert pct["A"] == 100.0
    assert pct["B"] == 0.0
    # Single-member EUROPE industry -> 100
    assert pct["G"] == 100.0
    # every name present
    assert set("ABCDEFG") <= set(pct.keys())


def test_fail_open_empty_and_missing_cols():
    # empty frame
    assert si.ranks(region="USA", stage_frame=pd.DataFrame()) == []
    assert si.name_industry_percentiles(stage_frame=pd.DataFrame()) == {}
    # missing required columns -> [] (fail-open, no crash)
    bad = pd.DataFrame([{"ticker": "X", "region": "USA"}])
    assert si.ranks(region="USA", stage_frame=bad) == []
    # unknown region -> []
    assert si.ranks(region="MARS", stage_frame=_frame()) == []


def test_build_writes_artifacts_display_tier(tmp_path: Path):
    contract = si.build(stage_frame=_frame(), root=tmp_path, asof="2026-07-20")
    assert contract["is_context_only"] is True
    assert contract["display_only"] is True
    ranks_p = tmp_path / "stage_analysis" / "industry_ranks.json"
    pct_p = tmp_path / "stage_analysis" / "industry_name_pctile.json"
    assert ranks_p.exists() and pct_p.exists()
    written = json.loads(ranks_p.read_text())
    assert "USA" in written["regions"]
    # ranks within a region are sorted ascending
    usa = written["regions"]["USA"]
    assert [r["rank"] for r in usa] == sorted(r["rank"] for r in usa)
    pct = json.loads(pct_p.read_text())
    assert pct["percentiles"]["A"] == 100.0


def test_all_region_concat_hint_and_per_region_rank1(tmp_path: Path):
    """FIX 3 — ranks are region-relative, so a concat 'All' view carries one
    rank-1/pctile-100 row PER region. The contract flags that (all_region_is_concat)
    and every row carries its region so the surface can default to one region."""
    contract = si.build(stage_frame=_frame(), root=tmp_path, asof="2026-07-20")
    assert contract["all_region_is_concat"] is True
    assert "all_region_note" in contract
    # Every region has exactly one rank-1 and one percentile-100 row (the concat
    # duplicate-leaders symptom the hint warns the designer about).
    for reg, rows in contract["regions"].items():
        assert sum(1 for r in rows if r["rank"] == 1) == 1
        assert sum(1 for r in rows if r["industry_percentile"] == 100.0) == 1
        assert all(r["region"] == reg for r in rows)   # region tags every row


def test_build_fail_open_no_frame_no_seed(tmp_path: Path):
    # No stage_frame and no backfill under tmp_path -> empty contract, no crash.
    contract = si.build(stage_frame=None, root=tmp_path, asof="2026-07-20")
    assert contract["n_industries"] == 0
    assert contract["regions"] == {}
    assert contract["status"] == "warn"
    assert contract["coverage"]["non_vacuous"] is False
    assert {"no_input_rows", "no_eligible_rows", "no_output_rows"} <= set(
        contract["coverage"]["issues"])


def test_prepare_live_frame_joins_reference_taxonomy_and_asof(tmp_path: Path):
    p = tmp_path / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"ticker": "AAA", "region": "N.Amer", "gics_industry": "Software",
         "gics_sub_industry": "Systems Software"},
        {"ticker": "BBB", "region": "N.Amer", "gics_industry": "Software",
         "gics_sub_industry": "Application Software"},
    ]).to_parquet(p)
    live = pd.DataFrame([
        {"ticker": "AAA", "stage": 2, "fresh": True, "weeks_in_stage": 1,
         "mansfield_rs": 8.0, "mansfield_rs_change": 2.0, "sata_score": 8},
        {"ticker": "BBB", "stage": 4, "fresh": False, "weeks_in_stage": 3,
         "mansfield_rs": -4.0, "mansfield_rs_change": -1.0, "sata_score": 2},
    ])
    prepared = si.prepare_live_frame(
        live, root=tmp_path, source_asof="2026-07-20",
    )
    assert prepared["region"].tolist() == ["USA", "USA"]
    assert prepared["industry_id"].tolist() == ["Software", "Software"]
    assert prepared["stage_flag"].tolist() == [2, 4]
    assert prepared["is_stage2_start"].tolist() == [True, False]
    assert set(prepared["stage_source_asof"]) == {"2026-07-20"}

    contract = si.build(stage_frame=prepared, root=tmp_path, asof="2026-07-20")
    assert contract["status"] == "ready"
    assert contract["coverage"]["taxonomy_coverage_pct"] == 100.0
    assert contract["coverage"]["freshness"]["status"] == "current"


def test_prepare_live_frame_does_not_treat_fresh_window_as_stage_start(tmp_path: Path):
    live = pd.DataFrame([
        {"ticker": "AAA", "region": "USA", "industry_id": "Software",
         "industry_name": "Software", "stage": 2, "fresh": True,
         "weeks_in_stage": 6, "mansfield_rs": 8.0,
         "mansfield_rs_change": 2.0},
    ])
    prepared = si.prepare_live_frame(live, root=tmp_path)
    assert prepared["is_stage2_start"].tolist() == [False]


def test_coverage_guard_marks_stale_source(tmp_path: Path):
    stale = _frame().assign(stage_source_asof="2026-07-19")
    contract = si.build(stage_frame=stale, root=tmp_path, asof="2026-07-20")
    assert contract["coverage"]["non_vacuous"] is True
    assert contract["status"] == "warn"
    assert contract["coverage"]["freshness"]["status"] == "stale"
    assert "source_asof_stale" in contract["coverage"]["issues"]


# ---------------------------------------------------------------------------
# Wave 8 §6.1 — the false-stale warning: judge freshness on the Stage-week
# plane when both sides carry one, falling back to the daily comparison only
# when the week plane cannot answer.
# ---------------------------------------------------------------------------
def test_coverage_week_plane_not_stale_despite_daily_lag():
    """Required §10 case: an Aug-20 build with an Aug-19 daily source and a
    target completed Stage week Aug-14 is NOT reported stale, because the
    classifier is weekly-native and the frame's own stage_week_end also
    resolves to Aug-14."""
    frame = _frame().assign(stage_source_asof="2026-08-19",
                            stage_week_end="2026-08-14")
    cov = si.coverage_snapshot(frame, expected_asof="2026-08-20",
                               output_rows=3, expected_stage_week="2026-08-14")
    assert cov["freshness"]["plane"] == "stage_week"
    assert cov["freshness"]["status"] == "current"
    assert cov["status"] == "ready"
    assert "source_asof_stale" not in cov["issues"]
    assert not any(i.startswith("source_stage_week_") for i in cov["issues"])
    # daily values stay in the payload for audit even though they did not
    # decide the freshness verdict.
    assert cov["freshness"]["source_asof"] == "2026-08-19"
    assert cov["freshness"]["expected_asof"] == "2026-08-20"
    assert cov["freshness"]["expected_stage_week"] == "2026-08-14"
    assert cov["freshness"]["source_stage_week"] == "2026-08-14"


def test_coverage_week_plane_flags_a_genuine_week_mismatch():
    frame = _frame().assign(stage_week_end="2026-06-26")
    cov = si.coverage_snapshot(frame, expected_asof="2026-08-20",
                               output_rows=3, expected_stage_week="2026-08-14")
    assert cov["freshness"]["plane"] == "stage_week"
    assert cov["freshness"]["status"] == "stale"
    assert "source_stage_week_stale" in cov["issues"]
    assert cov["status"] == "warn"


def test_coverage_falls_back_to_daily_plane_when_week_plane_unavailable():
    """No `stage_week_end` column on the frame -> the plane stays 'daily'
    even when the caller supplies `expected_stage_week`."""
    frame = _frame().assign(stage_source_asof="2026-07-19")
    cov = si.coverage_snapshot(frame, expected_asof="2026-07-20",
                               output_rows=3, expected_stage_week="2026-08-14")
    assert cov["freshness"]["plane"] == "daily"
    assert cov["freshness"]["status"] == "stale"
    assert "source_asof_stale" in cov["issues"]
    assert not any(i.startswith("source_stage_week_") for i in cov["issues"])


def test_build_threads_target_stage_week_into_coverage(tmp_path: Path):
    frame = _frame().assign(stage_source_asof="2026-08-19",
                            stage_week_end="2026-08-14")
    contract = si.build(stage_frame=frame, root=tmp_path, asof="2026-08-20",
                        target_stage_week="2026-08-14")
    assert contract["status"] == "ready"
    assert contract["coverage"]["freshness"]["plane"] == "stage_week"
    assert "source_asof_stale" not in contract["coverage"]["issues"]


# ---------------------------------------------------------------------------
# Wave 8 §6.3 — provenance text split: house-native `method` vs the
# EquityDesk historical `calibration` yardstick.
# ---------------------------------------------------------------------------
def test_method_and_calibration_blocks_are_split(tmp_path: Path):
    contract = si.build(stage_frame=_frame(), root=tmp_path, asof="2026-07-20")
    assert contract["method"]["plane"] == "completed W-FRI stage week"
    assert "House-native" in contract["method"]["live"]
    assert "OHLCV" in contract["method"]["live"]
    assert contract["calibration"]["target"] == (
        "stageanalysis_industry_ranks_weekly (EquityDesk)")
    assert "NOT an input" in contract["calibration"]["yardstick"]
    assert "rank rho" in contract["calibration"]["note"]
    # the old nested calibration.method key is gone — method is now top-level.
    assert "method" not in contract["calibration"]


# ---------------------------------------------------------------------------
# Calibration smoke — ordinal agreement vs EquityDesk industry_ranks.
# ---------------------------------------------------------------------------
_BACKFILL = (Path(__file__).resolve().parents[1] / "data" / "stage_analysis"
             / "backfill")


@pytest.mark.skipif(
    not (_BACKFILL / "stage_daily.parquet").exists()
    or not (_BACKFILL / "industry_ranks.parquet").exists(),
    reason="backfill parquets not present",
)
def test_calibration_smoke():
    """Rank ordering from our engine should positively correlate with theirs."""
    sd = pd.read_parquet(_BACKFILL / "stage_daily.parquet")
    ir = pd.read_parquet(_BACKFILL / "industry_ranks.parquet")
    last = ir["as_of_date"].max()

    agreements = []
    for reg in ("USA", "EUROPE", "ASIA"):
        ours = si.ranks(region=reg, stage_frame=sd)
        assert ours, f"no ranks for {reg}"
        theirs = ir[(ir["as_of_date"] == last) & (ir["region"] == reg)]
        t = {str(iid): int(rk) for iid, rk
             in zip(theirs["industry_id"], theirs["rank"])}
        o = {r["industry_id"]: r["rank"] for r in ours}
        common = sorted(set(t) & set(o))
        assert len(common) > 30
        tv = [t[i] for i in common]
        ov = [o[i] for i in common]
        # Spearman via pandas rank correlation (no scipy dependency).
        rho = pd.Series(tv).corr(pd.Series(ov), method="spearman")
        agreements.append(rho)
        assert rho > 0.2, f"{reg} rank spearman too low: {rho}"
    # mean ordinal agreement is meaningfully positive
    assert sum(agreements) / len(agreements) > 0.3


@pytest.mark.skipif(
    not (_BACKFILL / "stage_daily.parquet").exists()
    or not (_BACKFILL / "industry_ranks.parquet").exists(),
    reason="backfill parquets not present",
)
def test_calibration_floors():
    """HONESTY floors so the corrected calibration claims cannot silently drift.

    MEASURED on the backfill (not the previously-claimed ~99% bucket):
      - quartile `bucket` agreement with their industry_bucket ≈ 35%,
      - rank Spearman ≈ .36 (USA) / .49 (EUR) / .43 (ASIA).
    We floor bucket agreement at 0.25 and 0.55 (a wide band that brackets the
    measured 0.353 without pinning a brittle exact value) and each region's rank
    rho within [0.20, 0.70]. If a future change pushes bucket back toward the
    fictional 0.99, THIS test fails — forcing the docstring to be re-verified.
    """
    sd = pd.read_parquet(_BACKFILL / "stage_daily.parquet")
    ir = pd.read_parquet(_BACKFILL / "industry_ranks.parquet")
    last = ir["as_of_date"].max()
    theirs_last = ir[ir["as_of_date"] == last]

    bucket_ok = bucket_n = 0
    rhos = {}
    for reg in ("USA", "EUROPE", "ASIA"):
        ours = si.ranks(region=reg, stage_frame=sd)
        o = {r["industry_id"]: r for r in ours}
        tt = theirs_last[theirs_last["region"] == reg]
        tv, ov = [], []
        for row in tt.itertuples():
            r = o.get(str(row.industry_id))
            if r is None:
                continue
            bucket_n += 1
            if r["bucket"] == row.bucket:
                bucket_ok += 1
            tv.append(int(row.rank))
            ov.append(r["rank"])
        if len(tv) > 5:
            rhos[reg] = pd.Series(tv).corr(pd.Series(ov), method="spearman")

    assert bucket_n > 100, f"too few matched industries: {bucket_n}"
    bucket_frac = bucket_ok / bucket_n
    print(f"\n[SGA-2 industry calibration] bucket_agree={bucket_frac:.3f} "
          f"rank_rho={ {k: round(v, 3) for k, v in rhos.items()} }")
    # Bucket agreement is WEAK and honest — floored in a band around 0.35, NOT ~0.99.
    assert 0.25 <= bucket_frac <= 0.55, (
        f"bucket agreement {bucket_frac:.3f} outside the honest [0.25,0.55] band "
        "— re-verify the calibration docstring (it must NOT claim ~99%)")
    # Each region's rank rho is positive but modest (~0.4), not near-perfect.
    for reg, rho in rhos.items():
        assert 0.20 <= rho <= 0.70, f"{reg} rank rho {rho:.3f} outside [0.20,0.70]"


# ---------------------------------------------------------------------------
# Industry rank HISTORY — house-native weekly accrual (Wave 8 §7).
#
# The heatmap used to read a one-shot proprietary EquityDesk export
# (`data/stage_analysis/backfill/industry_ranks.parquet`) that is ABSENT from
# the committed backfill; the whole seed-reading path is DELETED (§7.4). All
# heatmap tests below drive the house-native
# `data/stage_analysis/industry_rank_history.jsonl` store instead — either
# directly via `append_industry_rank_history` (the real accrual path) or via
# a raw-write helper for hermetic grid-shape fixtures.
# ---------------------------------------------------------------------------
def _history_row(week: str, region: str, iid: str, name: str, rank: int,
                 score: float = 0.0, bucket: str = "Leading", n: int = 1) -> dict:
    return {"stage_week_end": week, "region": region, "industry_id": iid,
            "industry_name": name, "rank": rank, "score": score,
            "bucket": bucket, "n": n, "built": f"{week}T00:00:00Z",
            "source": "stage_industry.live"}


def _write_history_jsonl(root: Path, records: list[dict]) -> None:
    """Raw write of history records (bypasses the advance-guard) — used for
    hermetic heatmap grid-shape fixtures."""
    p = root / "stage_analysis" / "industry_rank_history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    p.write_text("\n".join(lines) + ("\n" if lines else ""))


def test_history_advances_on_a_healthy_current_build(tmp_path: Path):
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    coverage = {"non_vacuous": True, "status": "ready"}
    report = si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    assert report["advanced"] is True
    p = tmp_path / "stage_analysis" / "industry_rank_history.jsonl"
    assert p.exists()
    lines = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    assert len(lines) == len(all_ranks)
    assert {ln["stage_week_end"] for ln in lines} == {"2026-08-14"}
    # record fields map 1:1 onto what `_rank_region()` already returns.
    for rec in lines:
        for f in ("industry_id", "industry_name", "region", "n", "score",
                  "rank", "bucket", "industry_percentile"):
            assert f in rec


def test_history_does_not_advance_without_a_target_week(tmp_path: Path):
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    coverage = {"non_vacuous": True, "status": "ready"}
    report = si.append_industry_rank_history(all_ranks, None, coverage, tmp_path)
    assert report["advanced"] is False
    assert "no_target_stage_week" in report["reason"]
    assert not (tmp_path / "stage_analysis" / "industry_rank_history.jsonl").exists()


def test_history_does_not_advance_on_degraded_coverage(tmp_path: Path):
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    coverage = {"non_vacuous": True, "status": "warn",
                "issues": ["source_stage_week_stale"]}
    report = si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    assert report["advanced"] is False
    assert "coverage_not_ready" in report["reason"]
    assert not (tmp_path / "stage_analysis" / "industry_rank_history.jsonl").exists()


def test_history_does_not_advance_on_vacuous_output(tmp_path: Path):
    coverage = {"non_vacuous": False, "status": "warn"}
    report = si.append_industry_rank_history([], "2026-08-14", coverage, tmp_path)
    assert report["advanced"] is False
    assert "not_non_vacuous" in report["reason"]


def test_same_week_rerun_replaces_not_duplicates(tmp_path: Path):
    coverage = {"non_vacuous": True, "status": "ready"}
    first = si.ranks(region="USA", stage_frame=_frame())
    si.append_industry_rank_history(first, "2026-08-14", coverage, tmp_path)
    # A corrected same-week rebuild (e.g. a corrected OHLCV file) with
    # different scores must REPLACE the week's point, not duplicate it.
    second = si.ranks(region="USA", stage_frame=_frame())
    for r in second:
        r["score"] = r["score"] + 100.0
    si.append_industry_rank_history(second, "2026-08-14", coverage, tmp_path)
    p = tmp_path / "stage_analysis" / "industry_rank_history.jsonl"
    lines = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    assert len(lines) == len(first)          # still one week's worth
    assert all(ln["score"] > 50 for ln in lines)   # the corrected values won


def test_next_completed_week_yields_two_columns(tmp_path: Path):
    coverage = {"non_vacuous": True, "status": "ready"}
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    si.append_industry_rank_history(all_ranks, "2026-08-07", coverage, tmp_path)
    si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    grids = si.industry_heatmap(root=tmp_path)
    assert grids["USA"]["n_weeks"] == 2
    assert grids["USA"]["weeks"] == ["2026-08-14", "2026-08-07"]
    contract = si.build_industry_heatmap(root=tmp_path, asof="2026-08-20")
    assert contract["history"]["status"] == "accruing"
    assert contract["history"]["weeks_available"] == 2
    assert contract["history"]["first_week"] == "2026-08-07"
    assert contract["history"]["latest_week"] == "2026-08-14"


def test_history_key_is_stage_week_never_the_build_date(tmp_path: Path):
    coverage = {"non_vacuous": True, "status": "ready"}
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    # Two builds on DIFFERENT wall-clock dates, but the SAME target Stage
    # week, must never fork into two weekly points.
    si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    p = tmp_path / "stage_analysis" / "industry_rank_history.jsonl"
    lines = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    assert {ln["stage_week_end"] for ln in lines} == {"2026-08-14"}
    assert len(lines) == len(all_ranks)


def test_past_week_never_rewritten_by_a_later_run(tmp_path: Path):
    coverage = {"non_vacuous": True, "status": "ready"}
    week1 = si.ranks(region="USA", stage_frame=_frame())
    si.append_industry_rank_history(week1, "2026-08-07", coverage, tmp_path)
    p = tmp_path / "stage_analysis" / "industry_rank_history.jsonl"
    before = {ln["industry_id"]: ln["score"] for ln in
              (json.loads(x) for x in p.read_text().splitlines() if x.strip())}

    week2 = si.ranks(region="USA", stage_frame=_frame())
    for r in week2:
        r["score"] = r["score"] + 999.0
    si.append_industry_rank_history(week2, "2026-08-14", coverage, tmp_path)

    lines = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    after_week1 = {ln["industry_id"]: ln["score"] for ln in lines
                  if ln["stage_week_end"] == "2026-08-07"}
    assert after_week1 == before   # the past week's scores are untouched


def test_history_retention_keeps_newest_30_weeks(tmp_path: Path):
    from datetime import date, timedelta

    coverage = {"non_vacuous": True, "status": "ready"}
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    start = date(2026, 1, 2)  # a Friday
    weeks = [(start + timedelta(weeks=i)).isoformat() for i in range(32)]
    for wk in weeks:
        si.append_industry_rank_history(all_ranks, wk, coverage, tmp_path)
    p = tmp_path / "stage_analysis" / "industry_rank_history.jsonl"
    lines = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
    distinct = sorted({ln["stage_week_end"] for ln in lines})
    assert len(distinct) == 30
    assert distinct == sorted(weeks)[-30:]


# ---------------------------------------------------------------------------
# Industry rank HEATMAP (rank-over-time grid) — hermetic, reads the history.
# ---------------------------------------------------------------------------
def test_industry_heatmap_grid_shape(tmp_path: Path):
    weeks = ["2026-07-03", "2026-07-10", "2026-07-17"]
    rows = []
    for reg in ("USA", "EUROPE"):
        for wk in weeks:
            for iid, rk in (("10", 1), ("20", 2), ("30", 3)):
                rows.append(_history_row(wk, reg, iid, f"{reg}-{iid}", rk))
    _write_history_jsonl(tmp_path, rows)
    grids = si.industry_heatmap(root=tmp_path)
    assert set(grids.keys()) == {"USA", "EUROPE"}
    usa = grids["USA"]
    assert usa["weeks"] == ["2026-07-17", "2026-07-10", "2026-07-03"]
    assert usa["n_weeks"] == 3
    assert usa["n_industries"] == 3
    row0 = usa["rows"][0]
    assert row0["industry_id"] == "10"
    assert row0["ranks"] == [1, 1, 1]


def test_industry_heatmap_null_alignment(tmp_path: Path):
    """A cell missing for one week aligns to null, not a shifted rank."""
    rows = [
        _history_row("2026-07-03", "USA", "10", "A", 1),
        # industry 10 skips 2026-07-10, returns 2026-07-17
        _history_row("2026-07-17", "USA", "10", "A", 2),
    ]
    _write_history_jsonl(tmp_path, rows)
    grids = si.industry_heatmap(root=tmp_path)
    usa = grids["USA"]
    assert usa["weeks"] == ["2026-07-17", "2026-07-03"]
    r = usa["rows"][0]
    assert r["ranks"] == [2, 1]


def test_industry_heatmap_fail_open_missing_history(tmp_path: Path):
    # No history file under tmp_path -> {} (page renders an explicit
    # accruing/unavailable state, never a healthy-looking empty panel).
    assert si.industry_heatmap(root=tmp_path) == {}


def test_build_industry_heatmap_display_tier(tmp_path: Path):
    rows = []
    for reg in ("USA", "EUROPE"):
        for iid, rk in (("10", 1), ("20", 2)):
            rows.append(_history_row("2026-07-20", reg, iid, f"{reg}-{iid}", rk))
    _write_history_jsonl(tmp_path, rows)
    contract = si.build_industry_heatmap(root=tmp_path, asof="2026-07-20")
    assert contract["schema"] == "stage_industry_heatmap.v1"
    assert contract["is_context_only"] is True and contract["display_only"] is True
    assert contract["source"] == (
        "house-native stage industry rank history "
        "(data/stage_analysis/industry_rank_history.jsonl)")
    out_p = tmp_path / "stage_analysis" / "industry_heatmap.json"
    assert out_p.exists()
    written = json.loads(out_p.read_text())
    assert set(written["regions"].keys()) == {"USA", "EUROPE"}


# ---------------------------------------------------------------------------
# Wave 8 §7.4 — the heatmap's `history` accrual-status block.
# ---------------------------------------------------------------------------
def test_heatmap_history_block_unavailable_with_no_house_history(tmp_path: Path):
    """No accrued house history -> an explicit `unavailable` status, not a
    healthy-looking empty panel."""
    contract = si.build_industry_heatmap(root=tmp_path, asof="2026-08-20")
    assert contract["history"] == {
        "status": "unavailable", "weeks_available": 0, "weeks_target": 26,
        "first_week": None, "latest_week": None,
    }
    assert contract["regions"] == {}
    assert contract["n_regions"] == 0


def test_heatmap_history_block_first_valid_week_is_one_column(tmp_path: Path):
    coverage = {"non_vacuous": True, "status": "ready"}
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    contract = si.build_industry_heatmap(root=tmp_path, asof="2026-08-20")
    assert contract["history"]["status"] == "accruing"
    assert contract["history"]["weeks_available"] == 1
    assert contract["history"]["first_week"] == "2026-08-14"
    assert contract["history"]["latest_week"] == "2026-08-14"
    assert contract["regions"]["USA"]["n_weeks"] == 1
    assert contract["n_regions"] == 1


def test_heatmap_history_block_same_week_rerun_stays_one_column(tmp_path: Path):
    coverage = {"non_vacuous": True, "status": "ready"}
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    si.append_industry_rank_history(all_ranks, "2026-08-14", coverage, tmp_path)
    contract = si.build_industry_heatmap(root=tmp_path, asof="2026-08-20")
    assert contract["history"]["weeks_available"] == 1     # no duplicate
    assert contract["regions"]["USA"]["n_weeks"] == 1


def test_heatmap_history_block_ready_at_26_weeks(tmp_path: Path):
    from datetime import date, timedelta

    coverage = {"non_vacuous": True, "status": "ready"}
    all_ranks = si.ranks(region="USA", stage_frame=_frame())
    start = date(2026, 1, 2)
    for i in range(26):
        wk = (start + timedelta(weeks=i)).isoformat()
        si.append_industry_rank_history(all_ranks, wk, coverage, tmp_path)
    contract = si.build_industry_heatmap(root=tmp_path, asof="2026-08-20")
    assert contract["history"]["status"] == "ready"
    assert contract["history"]["weeks_available"] == 26
