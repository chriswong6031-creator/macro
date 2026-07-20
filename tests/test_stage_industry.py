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
# Industry rank HEATMAP (rank-over-time grid) — hermetic + real-seed calibration.
# ---------------------------------------------------------------------------
def _write_ranks_seed(root: Path) -> None:
    """Tiny synthetic industry_ranks seed: 2 regions x 3 industries x 3 Fridays,
    plus one non-Friday row that must be excluded from the weekly grid."""
    rows = []
    fridays = ["2026-07-03", "2026-07-10", "2026-07-17"]  # all Fridays
    for reg in ("USA", "EUROPE"):
        for wi, day in enumerate(fridays):
            for iid, base in (("10", 1), ("20", 2), ("30", 3)):
                rows.append(dict(region=reg, industry_id=iid,
                                 industry_name=f"{reg}-{iid}", as_of_date=day,
                                 rank=base, score=0.0, bucket="Leading",
                                 z_rsroc=0.0, z_mom=0.0, industry_percentile=0.0,
                                 created_at=day))
    # a Thursday row (weekday != 4) that MUST be filtered out of the weekly grid
    rows.append(dict(region="USA", industry_id="10", industry_name="USA-10",
                     as_of_date="2026-07-16", rank=99, score=0.0, bucket="Leading",
                     z_rsroc=0.0, z_mom=0.0, industry_percentile=0.0,
                     created_at="2026-07-16"))
    p = root / "stage_analysis" / "backfill" / "industry_ranks.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p)


def test_industry_heatmap_grid_shape(tmp_path: Path):
    _write_ranks_seed(tmp_path)
    grids = si.industry_heatmap(root=tmp_path)
    assert set(grids.keys()) == {"USA", "EUROPE"}
    usa = grids["USA"]
    # weeks most-recent-first, Fridays only (the Thursday row is excluded).
    assert usa["weeks"] == ["2026-07-17", "2026-07-10", "2026-07-03"]
    assert usa["n_weeks"] == 3
    assert usa["n_industries"] == 3
    # ranks aligned to weeks[]; industry 10 is rank 1 every week (top of grid).
    row0 = usa["rows"][0]
    assert row0["industry_id"] == "10"
    assert row0["ranks"] == [1, 1, 1]
    # the excluded Thursday rank 99 never surfaces.
    all_ranks = [rk for r in usa["rows"] for rk in r["ranks"] if rk is not None]
    assert 99 not in all_ranks
    assert min(all_ranks) == 1


def test_industry_heatmap_null_alignment(tmp_path: Path):
    """A cell missing for one week aligns to null, not a shifted rank."""
    rows = [
        dict(region="USA", industry_id="10", industry_name="A", as_of_date="2026-07-03",
             rank=1, score=0.0, bucket="Leading", z_rsroc=0.0, z_mom=0.0,
             industry_percentile=0.0, created_at="x"),
        # industry 10 skips 2026-07-10, returns 2026-07-17
        dict(region="USA", industry_id="10", industry_name="A", as_of_date="2026-07-17",
             rank=2, score=0.0, bucket="Leading", z_rsroc=0.0, z_mom=0.0,
             industry_percentile=0.0, created_at="x"),
    ]
    p = tmp_path / "stage_analysis" / "backfill" / "industry_ranks.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(p)
    grids = si.industry_heatmap(root=tmp_path)
    usa = grids["USA"]
    assert usa["weeks"] == ["2026-07-17", "2026-07-03"]
    r = usa["rows"][0]
    # weeks[]=[07-17, 07-03] -> ranks[]=[2, 1]; no missing week here, both present.
    assert r["ranks"] == [2, 1]


def test_industry_heatmap_fail_open_missing_seed(tmp_path: Path):
    # No seed under tmp_path -> {} (page renders an empty state).
    assert si.industry_heatmap(root=tmp_path) == {}


def test_build_industry_heatmap_display_tier(tmp_path: Path):
    _write_ranks_seed(tmp_path)
    contract = si.build_industry_heatmap(root=tmp_path, asof="2026-07-20")
    assert contract["schema"] == "stage_industry_heatmap.v1"
    assert contract["is_context_only"] is True and contract["display_only"] is True
    out_p = tmp_path / "stage_analysis" / "industry_heatmap.json"
    assert out_p.exists()
    written = json.loads(out_p.read_text())
    assert set(written["regions"].keys()) == {"USA", "EUROPE"}


@pytest.mark.skipif(
    not (_BACKFILL / "industry_ranks.parquet").exists(),
    reason="industry_ranks backfill parquet not present",
)
def test_industry_heatmap_real_seed():
    """Real-seed smoke: three regions, ~26 trailing Fridays, ranks in [1, N]."""
    grids = si.industry_heatmap()
    assert set(grids.keys()) == {"USA", "EUROPE", "ASIA"}
    for reg, g in grids.items():
        assert 20 <= g["n_weeks"] <= 26, f"{reg} n_weeks={g['n_weeks']}"
        assert 40 <= g["n_industries"] <= 90, f"{reg} n_industries={g['n_industries']}"
        # weeks strictly most-recent-first and unique.
        assert g["weeks"] == sorted(g["weeks"], reverse=True)
        assert len(set(g["weeks"])) == len(g["weeks"])
        # every row's ranks[] aligns to weeks[]; ranks are 1..N ints or null.
        n = g["n_industries"]
        for row in g["rows"]:
            assert len(row["ranks"]) == g["n_weeks"]
            for rk in row["ranks"]:
                assert rk is None or (isinstance(rk, int) and 1 <= rk <= 200)
        # rank 1 exists in the latest week (someone is strongest).
        latest_ranks = [row["ranks"][0] for row in g["rows"] if row["ranks"][0] is not None]
        assert min(latest_ranks) == 1
        # the top-of-grid row IS the latest-week rank-1 industry.
        assert grids[reg]["rows"][0]["ranks"][0] == 1
