"""SGA-2 W2 — Earnings-season / EC-industry-heatmap / comparison / table tests.

Covers the four Earnings-Calls surfaces added to engine/earnings_qual.py
(masterplan §1 surface D + §2 engines #4/#5).  All hermetic: each test writes a
tiny synthetic backfill parquet into a tmp `data/stage_analysis/backfill/` root
and exercises the pure aggregation — no network, no live stores, no LLM.

Assertions:
  1. ec_industry_heatmap aggregates weekly per-GICS-industry (count + means).
  2. earnings_comparison performs the QoQ delta join (current vs prior call).
  3. earnings_season splits Raisers (Δ>5) vs Decliners (Δ<-5) correctly.
  4. earnings_season emits a level1/level2 tag-frequency cloud.
  5. earnings_table caps to the latest N calls, newest first, with slide path.
  6. Every surface is fail-open on an EMPTY / missing seed (valid empty artifact).
  7. Every artifact carries the display-tier envelope (is_context_only + display_only).
  8. Tag parsing tolerates JSON-string, list, and empty cells.

Chinese strings (none needed here) would go through Write/Edit only per house law.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.earnings_qual as eq  # noqa: E402


# ── fixtures ────────────────────────────────────────────────────────────────
def _write_backfill(root: Path, records: list[dict]) -> None:
    """Write a synthetic earnings backfill parquet at the lane's expected path."""
    p = root / "data" / "stage_analysis" / "backfill" / "earnings_calls.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "document_ticker", "company_ticker", "company_name", "fiscal_quarter",
        "fiscal_year", "call_date", "gics_sector", "gics_industry_group",
        "gics_industry", "gics_subindustry", "earnings_call_sent",
        "earnings_call_perf", "earnings_call_combined", "earnings_call_pop",
        "positive_highlights", "negative_highlights", "key_quote",
        "level1_tags", "level2_tags", "file_path",
    ]
    df = pd.DataFrame(records)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df.to_parquet(p, index=False)


def _call(ticker, name, industry, date, sent, perf, combined,
          l1=None, l2=None, fp=None) -> dict:
    return {
        "company_ticker": f"{ticker} US",
        "document_ticker": ticker,
        "company_name": name,
        "gics_sector": "Information Technology",
        "gics_industry": industry,
        "call_date": date,
        "earnings_call_sent": sent,
        "earnings_call_perf": perf,
        "earnings_call_combined": combined,
        "level1_tags": json.dumps(l1) if l1 is not None else None,
        "level2_tags": json.dumps(l2) if l2 is not None else None,
        "file_path": fp,
    }


# ── 1. heatmap weekly aggregation ───────────────────────────────────────────
def test_ec_industry_heatmap_weekly_aggregation(tmp_path):
    # Two software names + one hardware name, all with calls in the same recent
    # week window → one Friday week, two industries.
    recs = [
        _call("AAA", "Alpha", "Software", "2026-07-10", 24, 4, 28),
        _call("BBB", "Beta", "Software", "2026-07-13", 20, 2, 22),
        _call("CCC", "Gamma", "Hardware", "2026-07-14", 18, 0, 18),
    ]
    _write_backfill(tmp_path, recs)
    out = eq.ec_industry_heatmap(root=tmp_path, weeks=4, write=True)
    rows = out["rows"]
    assert out["is_context_only"] is True and out["display_only"] is True
    # find the latest Friday week that contains Software
    sw = [r for r in rows if r["gics_industry"] == "Software"]
    hw = [r for r in rows if r["gics_industry"] == "Hardware"]
    assert sw and hw
    # In the most-recent week both software names are fresh → count 2, mean sent 22
    latest_week = max(r["week"] for r in sw)
    sw_latest = [r for r in sw if r["week"] == latest_week][0]
    assert sw_latest["companies_with_fresh_ec"] == 2
    assert sw_latest["avg_earnings_call_sent"] == pytest.approx(22.0)
    assert sw_latest["avg_earnings_call_combined"] == pytest.approx(25.0)
    # artifact was written
    assert (tmp_path / "data" / "stage_analysis" / "ec_industry.json").exists()


# ── 2. QoQ delta join (comparison) ──────────────────────────────────────────
def test_earnings_comparison_qoq_delta_join(tmp_path):
    recs = [
        _call("AAA", "Alpha", "Software", "2026-01-15", 20, 0, 20, l1=["a", "b"]),
        _call("AAA", "Alpha", "Software", "2026-04-15", 26, 4, 30, l1=["b", "c"]),
        _call("SOLO", "Solo", "Hardware", "2026-04-10", 10, 0, 10),  # only one call
    ]
    _write_backfill(tmp_path, recs)
    out = eq.earnings_comparison(root=tmp_path, write=True)
    rows = {r["ticker"]: r for r in out["rows"]}
    # Solo (single call) is excluded — comparison needs two calls
    assert "SOLO" not in rows
    a = rows["AAA"]
    assert a["current_combined"] == 30 and a["prior_combined"] == 20
    assert a["delta_combined"] == 10
    assert a["both_scored"] is True          # FIX 2 — both quarters genuinely scored
    # tag diff join
    assert a["new_tags"] == ["c"] and a["dropped_tags"] == ["a"]


# ── 2b. FIX 2 — unscored-quarter gaps must NOT top the swing ranking ─────────
def test_earnings_comparison_unscored_zero_excluded_from_top(tmp_path):
    """A combined of 0 marks an UNSCORED call, not a true zero. A 0-vs-38 pair is
    a false ±38 swing — it stays viewable (both_scored=false) but is floored below
    every genuine both-scored swing so it can't lead the biggest-tone-swings list."""
    recs = [
        # GENUINE swing: 5 -> 12 (both scored), a modest +7.
        _call("REAL", "Real", "Software", "2026-01-15", 6, -1, 5),
        _call("REAL", "Real", "Software", "2026-04-15", 12, 0, 12),
        # FALSE swing: 38 -> 0 (current unscored). Raw |delta|=38 >> the real +7,
        # so the OLD code ranked this bogus row at the very top.
        _call("GAP", "Gappy", "Software", "2026-01-10", 30, 8, 38),
        _call("GAP", "Gappy", "Software", "2026-04-10", 5, -2, 0),   # combined==0 → unscored
    ]
    _write_backfill(tmp_path, recs)
    out = eq.earnings_comparison(root=tmp_path, write=True)
    rows = {r["ticker"]: r for r in out["rows"]}

    # Both rows are still VIEWABLE (excluded only from the top ranking).
    assert "REAL" in rows and "GAP" in rows
    assert rows["GAP"]["both_scored"] is False    # straddles an unscored quarter
    assert rows["GAP"]["current_scored"] is False and rows["GAP"]["prior_scored"] is True
    assert rows["REAL"]["both_scored"] is True

    # Despite |GAP delta|=38 >> |REAL delta|=7, the genuine scored swing leads and
    # the unscored-straddling row is floored below every both_scored row.
    order = [r["ticker"] for r in out["rows"]]
    assert order.index("REAL") < order.index("GAP")
    first_unscored = next(i for i, r in enumerate(out["rows"]) if not r["both_scored"])
    assert all(out["rows"][i]["both_scored"] for i in range(first_unscored))
    # disclosure counts
    assert out["n_scored"] == 1 and out["n_total"] == 2


# ── 3. raiser / decliner split ──────────────────────────────────────────────
def test_earnings_season_raiser_decliner_split(tmp_path):
    # Same quarter (2026Q2) — one clear raiser (+10), one clear decliner (-10),
    # one flat (Δ=+2, inside the ±5 dead-band → neither side).
    recs = [
        _call("RIS", "Riser", "Software", "2026-01-20", 15, 0, 15),
        _call("RIS", "Riser", "Software", "2026-05-20", 22, 3, 25),   # Δ +10 raiser
        _call("DEC", "Decliner", "Software", "2026-01-21", 30, 0, 30),
        _call("DEC", "Decliner", "Software", "2026-05-21", 18, 2, 20),  # Δ -10 decliner
        _call("FLT", "Flat", "Hardware", "2026-01-22", 20, 0, 20),
        _call("FLT", "Flat", "Hardware", "2026-05-22", 21, 1, 22),      # Δ +2 → neither
    ]
    _write_backfill(tmp_path, recs)
    out = eq.earnings_season(quarter="2026Q2", root=tmp_path, write=True)
    assert len(out["quarters"]) == 1
    q = out["quarters"][0]
    assert q["quarter"] == "2026Q2"
    assert q["raisers"]["count"] == 1
    assert q["decliners"]["count"] == 1
    # flat name counted in n_scored_qoq but in neither bucket
    assert q["n_scored_qoq"] == 3


# ── 4. tag-frequency cloud ──────────────────────────────────────────────────
def test_earnings_season_tag_frequency_cloud(tmp_path):
    recs = [
        _call("R1", "R1", "Software", "2026-01-01", 10, 0, 10),
        _call("R1", "R1", "Software", "2026-05-01", 25, 0, 25,
              l1=["margin_expansion", "new_product"]),   # Δ +15 raiser
        _call("R2", "R2", "Software", "2026-01-02", 10, 0, 10),
        _call("R2", "R2", "Software", "2026-05-02", 24, 0, 24,
              l1=["margin_expansion"]),                    # Δ +14 raiser
    ]
    _write_backfill(tmp_path, recs)
    out = eq.earnings_season(quarter="2026Q2", root=tmp_path, write=True)
    q = out["quarters"][0]
    cloud = {t["tag"]: t["count"] for t in q["raisers"]["level1_tags"]}
    assert cloud["margin_expansion"] == 2
    assert cloud["new_product"] == 1
    # industry allocation reflects both raisers in Software
    alloc = {a["gics_industry"]: a["count"] for a in q["raisers"]["industry_allocation"]}
    assert alloc["Software"] == 2


# ── 5. earnings_table cap + ordering + slide path ───────────────────────────
def test_earnings_table_cap_and_order(tmp_path):
    recs = [
        _call(f"T{i}", f"T{i}", "Software", f"2026-03-{10 + i:02d}",
              20, 0, 20, fp=("slide.pdf" if i == 0 else None))
        for i in range(10)
    ]
    # give the newest a distinct latest date + slide
    recs.append(_call("NEW", "Newest", "Hardware", "2026-07-17", 30, 5, 35,
                      l1=["beat_and_raise"], fp="new_slide.pdf"))
    _write_backfill(tmp_path, recs)
    out = eq.earnings_table(root=tmp_path, cap=5, write=True)
    rows = out["rows"]
    assert len(rows) == 5                      # capped
    assert rows[0]["ticker"] == "NEW"          # newest first
    assert rows[0]["call_date"] == "2026-07-17"
    assert rows[0]["file_path"] == "new_slide.pdf"
    assert rows[0]["level1_tags"] == ["beat_and_raise"]
    assert out["cap"] == 5


# ── 6. fail-open on empty / missing seed ────────────────────────────────────
def test_all_surfaces_fail_open_empty(tmp_path):
    # No backfill parquet written at all.
    for fn, key in (
        (eq.ec_industry_heatmap, "n_industries"),
        (eq.ec_industry_heatmap_grid, "n_regions"),
        (eq.earnings_season, "n_quarters"),
        (eq.earnings_comparison, "n_rows"),
        (eq.earnings_table, "n_rows"),
    ):
        out = fn(root=tmp_path, write=True)
        assert out["is_context_only"] is True
        assert out["display_only"] is True
        # empty but structurally valid
        assert out.get(key) == 0 or out.get(key) == 0
    # build_all also must not raise
    res = eq.build_all_earnings_surfaces(root=tmp_path)
    assert set(res) == {"ec_industry", "ec_industry_grid", "earnings_season",
                        "earnings_compare", "earnings_table"}


# ── 7. display-tier envelope on every artifact ──────────────────────────────
def test_display_tier_envelope_on_disk(tmp_path):
    _write_backfill(tmp_path, [
        _call("AAA", "Alpha", "Software", "2026-04-15", 20, 0, 20),
        _call("AAA", "Alpha", "Software", "2026-07-15", 25, 0, 25),
    ])
    eq.build_all_earnings_surfaces(root=tmp_path)
    base = tmp_path / "data" / "stage_analysis"
    for name in ("ec_industry", "earnings_season", "earnings_compare", "earnings_table"):
        obj = json.loads((base / f"{name}.json").read_text())
        assert obj["is_context_only"] is True, name
        assert obj["display_only"] is True, name
        assert obj["surface"]


# ── 8. tag parsing tolerance ────────────────────────────────────────────────
def test_parse_tag_list_tolerance():
    assert eq._parse_tag_list(json.dumps(["a", "b"])) == ["a", "b"]
    assert eq._parse_tag_list(["x", "y"]) == ["x", "y"]
    assert eq._parse_tag_list(None) == []
    assert eq._parse_tag_list("") == []
    assert eq._parse_tag_list("   ") == []
    # comma-separated non-JSON fallback
    assert eq._parse_tag_list("alpha, beta") == ["alpha", "beta"]


# ── 9. earnings-surface advice scrub (item 9) ───────────────────────────────
def test_earnings_table_scrubs_advice(tmp_path):
    """Free-text highlights + key_quote + tags on the earnings TABLE surface are
    routed through the SAME advice scrubber as stage_research (item 9)."""
    rec = {
        "document_ticker": "AAA",
        "company_ticker": "AAA US",
        "company_name": "Alpha",
        "gics_sector": "Information Technology",
        "gics_industry": "Software",
        "call_date": "2026-07-15",
        "earnings_call_sent": 20,
        "earnings_call_perf": 0,
        "earnings_call_combined": 20,
        "positive_highlights": "Investors should buy this; our price target is high.",
        "negative_highlights": "We recommend you sell the weak segment.",
        "key_quote": "Go long here — a strong buy.",
        "level1_tags": json.dumps(["strong buy", "demand_acceleration"]),
        "level2_tags": None,
        "file_path": None,
    }
    _write_backfill(tmp_path, [rec])
    out = eq.earnings_table(root=tmp_path)
    r = out["rows"][0]
    blob = " ".join(str(r.get(k) or "") for k in
                    ("positive_highlights", "negative_highlights", "key_quote"))
    blob += " " + " ".join(r.get("level1_tags") or [])
    low = blob.lower()
    for banned in ("price target", "strong buy", "we recommend", "go long", " buy ", " sell "):
        assert banned not in f" {low} ", f"advice leaked: {banned!r} in {blob!r}"


# ── 10. EC-industry-heatmap calibration vs the committed seed (item 6) ───────
_BACKFILL_EC = (Path(__file__).resolve().parents[1] / "data" / "stage_analysis"
                / "backfill" / "ec_industry.parquet")
_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not _BACKFILL_EC.exists(),
                    reason="ec_industry backfill parquet absent")
def test_ec_industry_calibration():
    """Region-aggregate their ec_industry.parquet and check ec_industry_heatmap()
    tracks it. MEASURED (NOT the previously-claimed MAE≈1.0 / r≈0.85):
        combined r ≈ 0.97 (faithful),  count MAE ≈ 3.9 (coarse volume proxy —
        our seed lacks their per-region split, so we sum a name across regions).
    Floors chosen wide enough to bracket the measured values without pinning a
    brittle exact number, but tight enough to catch a real regression or a
    re-inflated claim.
    """
    import numpy as np

    their = pd.read_parquet(_BACKFILL_EC)
    their["week"] = pd.to_datetime(their["as_of_date"]).dt.date.astype(str)
    their["c"] = pd.to_numeric(their["companies_with_fresh_ec"], errors="coerce")
    their["comb"] = pd.to_numeric(their["avg_earnings_call_combined"], errors="coerce")
    their["comb_wsum"] = their["c"] * their["comb"]
    # region-aggregate: sum counts, count-weighted mean of combined per (week,ind)
    g = their.groupby(["week", "gics_industry_name"]).agg(
        count=("c", "sum"), comb_wsum=("comb_wsum", "sum"),
        c2=("c", "sum")).reset_index()
    g["their_comb"] = g["comb_wsum"] / g["c2"]
    tcount = {(r.week, r.gics_industry_name): r.count for r in g.itertuples()}
    tcomb = {(r.week, r.gics_industry_name): r.their_comb for r in g.itertuples()}

    out = eq.ec_industry_heatmap(root=str(_REPO_ROOT), weeks=26, write=False)
    cnt_err, ours_c, theirs_c = [], [], []
    for row in out["rows"]:
        k = (row["week"], row["gics_industry"])
        if k not in tcount:
            continue
        cnt_err.append(abs(row["companies_with_fresh_ec"] - tcount[k]))
        oc, tc = row["avg_earnings_call_combined"], tcomb[k]
        if oc == oc and tc == tc:  # not NaN
            ours_c.append(oc)
            theirs_c.append(tc)

    assert len(cnt_err) > 200, f"too few matched (week,industry) rows: {len(cnt_err)}"
    mae = float(np.mean(cnt_err))
    r = float(np.corrcoef(ours_c, theirs_c)[0, 1])
    print(f"\n[SGA-2 EC calibration] n={len(cnt_err)} count_MAE={mae:.3f} combined_r={r:.3f}")
    # combined value is the genuine fidelity metric — floor it high.
    assert r > 0.85, f"combined r {r:.3f} too low (claim is ~0.97)"
    # count MAE is a coarse volume proxy — ceiling it honestly (NOT ~1.0).
    assert mae < 8.0, f"count MAE {mae:.3f} unexpectedly large — investigate the join"


# ── EC industry heatmap GRID (per-region matrix form) ───────────────────────
def _write_ec_grid_seed(root: Path, records: list[dict]) -> None:
    """Write a synthetic ec_industry seed (the per-region weekly aggregates)."""
    p = root / "data" / "stage_analysis" / "backfill" / "ec_industry.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = ["id", "as_of_date", "region", "gics_industry_id", "gics_industry_name",
            "companies_with_fresh_ec", "avg_earnings_call_sent",
            "avg_earnings_call_perf", "avg_earnings_call_combined", "updated_at"]
    pd.DataFrame(records, columns=cols).to_parquet(p)


def test_ec_grid_shape_and_order(tmp_path: Path):
    """Grid = per-region matrix; rows ordered by latest-week combined desc; cells
    align {combined,count} to weeks[]; a missing week aligns to null."""
    recs = []
    fridays = ["2026-07-03", "2026-07-10", "2026-07-17"]  # all Fridays
    # USA: two industries, HighInd always above LowInd on the latest week.
    for wi, day in enumerate(fridays):
        recs.append(dict(id=f"h{wi}", as_of_date=day, region="USA",
                         gics_industry_id="100", gics_industry_name="HighInd",
                         companies_with_fresh_ec=10 + wi, avg_earnings_call_sent=0.0,
                         avg_earnings_call_perf=0.0,
                         avg_earnings_call_combined=40.0 + wi, updated_at=day))
    # LowInd skips the middle week -> that cell must be null in the grid.
    for day, comb in (("2026-07-03", 5.0), ("2026-07-17", 8.0)):
        recs.append(dict(id=f"l{day}", as_of_date=day, region="USA",
                         gics_industry_id="200", gics_industry_name="LowInd",
                         companies_with_fresh_ec=3, avg_earnings_call_sent=0.0,
                         avg_earnings_call_perf=0.0,
                         avg_earnings_call_combined=comb, updated_at=day))
    # EUROPE isolation row (separate region key).
    recs.append(dict(id="e0", as_of_date="2026-07-17", region="EUROPE",
                     gics_industry_id="300", gics_industry_name="EuroInd",
                     companies_with_fresh_ec=2, avg_earnings_call_sent=0.0,
                     avg_earnings_call_perf=0.0,
                     avg_earnings_call_combined=15.0, updated_at="2026-07-17"))
    _write_ec_grid_seed(tmp_path, recs)

    out = eq.ec_industry_heatmap_grid(root=str(tmp_path), weeks=26, write=False)
    assert out["is_context_only"] is True and out["display_only"] is True
    regions = out["regions"]
    assert set(regions.keys()) == {"USA", "EUROPE"}
    usa = regions["USA"]
    assert usa["weeks"] == ["2026-07-17", "2026-07-10", "2026-07-03"]
    assert usa["n_weeks"] == 3 and usa["n_industries"] == 2
    # HighInd (latest combined 42) sorts above LowInd (latest combined 8).
    assert usa["rows"][0]["industry"] == "HighInd"
    assert usa["rows"][1]["industry"] == "LowInd"
    # cells align {combined,count} to weeks[]; middle week is null for LowInd.
    high = usa["rows"][0]["cells"]
    assert [c["combined"] for c in high] == [42.0, 41.0, 40.0]
    assert [c["count"] for c in high] == [12, 11, 10]
    low = usa["rows"][1]["cells"]
    assert low[0]["combined"] == 8.0        # 2026-07-17
    assert low[1] is None                   # 2026-07-10 skipped
    assert low[2]["combined"] == 5.0        # 2026-07-03


def test_ec_grid_fail_open_missing_seed(tmp_path: Path):
    # No seed under tmp_path -> empty regions, valid envelope, no crash.
    out = eq.ec_industry_heatmap_grid(root=str(tmp_path), write=False)
    assert out["regions"] == {}
    assert out["n_regions"] == 0
    assert out["is_context_only"] is True and out["display_only"] is True


def test_ec_grid_writes_artifact(tmp_path: Path):
    _write_ec_grid_seed(tmp_path, [dict(
        id="x", as_of_date="2026-07-17", region="USA", gics_industry_id="100",
        gics_industry_name="Ind", companies_with_fresh_ec=4,
        avg_earnings_call_sent=0.0, avg_earnings_call_perf=0.0,
        avg_earnings_call_combined=10.0, updated_at="2026-07-17")])
    eq.ec_industry_heatmap_grid(root=str(tmp_path), write=True)
    p = tmp_path / "data" / "stage_analysis" / "ec_industry_heatmap.json"
    assert p.exists()
    written = json.loads(p.read_text())
    assert written["surface"] == "ec_industry_heatmap_grid"
    assert "USA" in written["regions"]


@pytest.mark.skipif(not _BACKFILL_EC.exists(),
                    reason="ec_industry backfill parquet not present")
def test_ec_grid_real_seed():
    """Real-seed smoke: three regions, ~26 trailing Fridays, cells well-formed."""
    out = eq.ec_industry_heatmap_grid(root=str(_REPO_ROOT), weeks=26, write=False)
    regions = out["regions"]
    assert set(regions.keys()) == {"USA", "EUROPE", "ASIA"}
    for reg, g in regions.items():
        assert g["n_weeks"] == 26, f"{reg} n_weeks={g['n_weeks']}"
        assert g["n_industries"] >= 20, f"{reg} n_industries={g['n_industries']}"
        # weeks most-recent-first and unique.
        assert g["weeks"] == sorted(g["weeks"], reverse=True)
        assert len(set(g["weeks"])) == len(g["weeks"])
        for row in g["rows"]:
            assert len(row["cells"]) == g["n_weeks"]
            for c in row["cells"]:
                if c is not None:
                    assert set(c.keys()) == {"combined", "count"}
                    assert c["combined"] is None or isinstance(c["combined"], float)
                    assert isinstance(c["count"], int)
        # rows sorted by latest-week combined descending (nulls/absences last).
        latest = [row["cells"][0]["combined"] for row in g["rows"]
                  if row["cells"][0] is not None
                  and row["cells"][0]["combined"] is not None]
        assert latest == sorted(latest, reverse=True)
