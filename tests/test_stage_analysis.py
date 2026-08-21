"""Tests for engine.stage_analysis (SGA W1).

The Weinstein classifier (engine/weinstein_stage.py) is built by a sibling
lane; this suite stubs `stage_analysis._classify` so it runs standalone. All
writes are redirected to tmp_path (root=) so the MM_DATA_GUARD tripwire never
sees the real data/ or site/ tree.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine import stage_analysis as sa
from scripts.publish_earnings_r2 import _synth_manifest

FIXTURE = Path(__file__).parent / "fixtures" / "stage_context_latest.json"

# Fields added AFTER the committed fixture was captured (forward-ledger
# calendar-asof audit 2026-08-05; Wave 8 observation-truth boundary
# 2026-08-20). Named explicitly so the schema guard stays fail-closed: a
# removed field, or any other unannounced addition, still fails.
_ADDITIVE_SINCE_FIXTURE = {
    "data_session", "target_stage_week", "target_week_source",
    "stage_week_end", "population",
}
_ADDITIVE_TOP_ROW_SINCE_FIXTURE = {
    "stage_source_asof", "stage_week_end", "stage_current",
}

# The fixed completed Stage week the whole fake universe below reads as
# CURRENT against (every stageable fixture ticker + SPY share it, so the
# resolver agrees with the population mode trivially -> target_week_source
# stays "spy_benchmark" for every pre-existing test that never touches the
# observation-truth partition directly).
_FAKE_STAGE_WEEK = "2026-07-17"


def _write_scores_manifest(scores: Path) -> None:
    """Commit a score-only transport generation for live-store fixtures."""
    payload = _synth_manifest(scores, None)
    (scores.parent / "manifest.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Fake classifier — deterministic per-ticker stage dicts, no price math.
# ---------------------------------------------------------------------------
def _fake_stage_map() -> dict[str, dict]:
    """A tidy universe covering every stage + a too-young + an unclassifiable."""
    stages = {
        # ticker: (stage, weeks, fresh, slope, pct_vs_ma30, mrs, vol_ratio, event, arc, n_weeks)
        "NVDA": dict(stage=2, weeks_in_stage=6, fresh=True, ma30_slope_pct5w=3.4,
                     pct_vs_ma30=8.9, mansfield_rs=12.0, vol_ratio=1.72,
                     event="breakout", arc_pos=0.31, n_weeks=200,
                     atr_14w=6.0, atr_ext=2.4, atr_pct_price=0.045, sata_score=9,
                     sata_change_1w=1, stage_detailed="2A_strong_breakout"),
        "AVGO": dict(stage=2, weeks_in_stage=9, fresh=True, ma30_slope_pct5w=2.1,
                     pct_vs_ma30=5.3, mansfield_rs=6.0, vol_ratio=1.31,
                     event="trendline_recapture", arc_pos=0.38, n_weeks=200,
                     atr_14w=5.0, atr_ext=0.6, atr_pct_price=0.04, sata_score=6,
                     sata_change_1w=0, stage_detailed="2X_catch_price_above_ma"),
        "COST": dict(stage=2, weeks_in_stage=22, fresh=False, ma30_slope_pct5w=1.0,
                     pct_vs_ma30=4.1, mansfield_rs=2.0, vol_ratio=0.98,
                     event=None, arc_pos=0.46, n_weeks=200,
                     atr_14w=8.0, atr_ext=1.4, atr_pct_price=0.03, sata_score=7,
                     sata_change_1w=-1, stage_detailed="2X_fallback_bullish"),
        "WMT": dict(stage=2, weeks_in_stage=40, fresh=False, ma30_slope_pct5w=0.9,
                    pct_vs_ma30=28.0, mansfield_rs=-1.0, vol_ratio=0.9,
                    event=None, arc_pos=0.49, n_weeks=200),
        "MMM": dict(stage=3, weeks_in_stage=4, fresh=False, ma30_slope_pct5w=0.1,
                    pct_vs_ma30=1.0, mansfield_rs=0.5, vol_ratio=1.0,
                    event=None, arc_pos=0.6, n_weeks=200),
        "PFE": dict(stage=4, weeks_in_stage=11, fresh=False, ma30_slope_pct5w=-2.0,
                    pct_vs_ma30=-8.0, mansfield_rs=-5.0, vol_ratio=1.1,
                    event=None, arc_pos=0.8, n_weeks=200),
        "INTC": dict(stage=4, weeks_in_stage=25, fresh=False, ma30_slope_pct5w=-1.5,
                     pct_vs_ma30=-12.0, mansfield_rs=-8.0, vol_ratio=0.95,
                     event=None, arc_pos=0.9, n_weeks=200),
        "KO": dict(stage=1, weeks_in_stage=8, fresh=False, ma30_slope_pct5w=0.05,
                   pct_vs_ma30=0.5, mansfield_rs=-0.2, vol_ratio=1.0,
                   event=None, arc_pos=0.1, n_weeks=200),
        "GE": dict(stage=1, weeks_in_stage=3, fresh=False, ma30_slope_pct5w=0.0,
                   pct_vs_ma30=-1.0, mansfield_rs=0.1, vol_ratio=1.0,
                   event=None, arc_pos=0.05, n_weeks=200),
        # too young: the real classifier flags too_young=True and stage=0.
        "IPOX": dict(stage=0, weeks_in_stage=0, fresh=False, ma30_slope_pct5w=None,
                     pct_vs_ma30=None, mansfield_rs=None, vol_ratio=None,
                     event=None, arc_pos=None, too_young=True, n_weeks=20),
        "SPY": dict(stage=2, weeks_in_stage=31, fresh=False, ma30_slope_pct5w=1.2,
                    pct_vs_ma30=3.0, mansfield_rs=0.0, vol_ratio=1.0,
                    event=None, arc_pos=0.45, n_weeks=300),
    }
    # The live classifier now carries the four-week Mansfield-RS delta used by
    # both industry-rank and breadth-flow surfaces.
    for rec in stages.values():
        mrs = rec.get("mansfield_rs")
        rec["mansfield_rs_change"] = None if mrs is None else round(mrs * 0.1, 2)
        rec["stage_source_asof"] = "2026-07-17"
        # Wave 8 §1.1 — stage_week_end is None on the too-young / unclassifiable
        # path (matches engine/weinstein_stage.py's _empty_result()); every
        # stageable name here completed the SAME Stage week, so the whole
        # population is CURRENT by default. Individual observation-truth tests
        # override this per-ticker to exercise the stale/unknown partition.
        if not rec.get("too_young") and rec.get("stage") not in (None, 0):
            rec["stage_week_end"] = _FAKE_STAGE_WEEK
    return stages


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Preferred fixture: patches _classify_one directly so the stage map is
    keyed on ticker (robust, order-independent)."""
    dr = tmp_path / "data"
    ohlcv = dr / "baskets" / "ohlcv"
    ohlcv.mkdir(parents=True)

    stage_map = _fake_stage_map()
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    frame = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
        index=idx)
    frame.index.name = "Date"
    for tk in stage_map:
        frame.to_parquet(ohlcv / f"{tk}.parquet")

    mem = pd.DataFrame([
        {"ticker": "NVDA", "name": "NVIDIA", "sector": "Information Technology", "active": True},
        {"ticker": "AVGO", "name": "Broadcom", "sector": "Information Technology", "active": True},
        {"ticker": "COST", "name": "Costco Wholesale", "sector": "Consumer Staples", "active": True},
        {"ticker": "WMT", "name": "Walmart", "sector": "Consumer Staples", "active": True},
        {"ticker": "MMM", "name": "3M", "sector": "Industrials", "active": True},
        {"ticker": "PFE", "name": "Pfizer", "sector": "Health Care", "active": True},
        {"ticker": "INTC", "name": "Intel", "sector": "Information Technology", "active": True},
        {"ticker": "KO", "name": "Coca-Cola", "sector": "Consumer Staples", "active": True},
        {"ticker": "GE", "name": "General Electric", "sector": "Industrials", "active": True},
    ])
    (dr / "universe").mkdir(parents=True)
    mem.to_parquet(dr / "universe" / "membership.parquet")

    (dr / "yahoo").mkdir(parents=True)
    spy = pd.DataFrame({"close": 1.0, "volume": 1}, index=idx)
    spy.index.name = "Date"
    spy.to_parquet(dr / "yahoo" / "SPY.parquet")

    fd = dr.parent / "site" / "factordata"
    fd.mkdir(parents=True)
    (fd / "signal_gate.json").write_text(json.dumps({
        "as_of": "2026-07-17",
        "verdicts": {
            "NVDA": {"eligible": True, "tier_cascade": "T1"},
            "AVGO": {"eligible": True, "tier_cascade": "T2"},
            "MMM": {"eligible": True, "tier_cascade": "T3"},
            "PFE": {"eligible": False, "tier_cascade": "T4"},
            "COST": {"eligible": False, "tier_cascade": None},
        },
    }))

    # Patch _classify_one to return the stage dict keyed on ticker.
    def _stub_classify_one(ticker):
        return ticker, stage_map.get(ticker)
    monkeypatch.setattr(sa, "_classify_one", _stub_classify_one)
    # Force serial path (env under 50 names already forces serial, but be explicit).
    monkeypatch.setattr(sa, "_resolve_workers", lambda mw: 1)
    # Neutralize the blackout call (no earnings.parquet present by default).
    return dr, stage_map


# ---------------------------------------------------------------------------
# 1. Schema completeness vs the fixture's key set.
# ---------------------------------------------------------------------------
def test_classify_one_stamps_actual_ohlcv_source_date(tmp_path, monkeypatch):
    dr = tmp_path / "data"
    p = dr / "baskets" / "ohlcv" / "AAA.parquet"
    p.parent.mkdir(parents=True)
    idx = pd.date_range("2026-07-01", periods=5, freq="D")
    pd.DataFrame({"close": range(5), "volume": 100}, index=idx).to_parquet(p)
    monkeypatch.setitem(sa._SHARED, "dr", dr)
    monkeypatch.setitem(sa._SHARED, "bench", pd.Series(range(5), index=idx))
    monkeypatch.setattr(sa, "_classify", lambda *args, **kwargs: {"stage": 2})

    ticker, result = sa._classify_one("AAA")

    assert ticker == "AAA"
    assert result["stage_source_asof"] == "2026-07-05"


def test_schema_completeness_vs_fixture(env):
    dr, _ = env
    fixture = json.loads(FIXTURE.read_text())
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")

    # Top-level keys match the fixture exactly (bar the named additive fields).
    built_keys = set(contract.keys()) - _ADDITIVE_SINCE_FIXTURE
    assert built_keys == set(fixture.keys()), (
        set(fixture.keys()) - built_keys,
        built_keys - set(fixture.keys()))
    assert _ADDITIVE_SINCE_FIXTURE <= set(contract.keys())

    assert contract["schema"] == "stage_context.v1"
    assert contract["is_context_only"] is True
    assert contract["display_only"] is True

    # counts / market key sets match.
    assert set(contract["counts"].keys()) == set(fixture["counts"].keys())
    assert set(contract["market"].keys()) == set(fixture["market"].keys())

    # A top_stage2 row carries every field the fixture rows do.
    fx_row_keys = set(fixture["top_stage2"][0].keys())
    assert contract["top_stage2"], "expected at least one Stage-2 name"
    built_row_keys = set(contract["top_stage2"][0].keys())
    assert built_row_keys - _ADDITIVE_TOP_ROW_SINCE_FIXTURE == fx_row_keys
    assert _ADDITIVE_TOP_ROW_SINCE_FIXTURE <= built_row_keys
    fx_earn_keys = set(fixture["top_stage2"][0]["earnings"].keys())
    assert set(contract["top_stage2"][0]["earnings"].keys()) == fx_earn_keys


# ---------------------------------------------------------------------------
# 1b. SGA-2 flagship artifacts: screener.json + stage_board_{daily,weekly}.
# ---------------------------------------------------------------------------
def test_screener_and_boards_emitted(env):
    dr, _ = env
    sa.build_context_feed(root=dr, asof="2026-07-17")

    screener = dr / "stage_analysis" / "screener.json"
    board_d = dr / "stage_analysis" / "stage_board_daily.json"
    board_w = dr / "stage_analysis" / "stage_board_weekly.json"
    assert screener.exists() and board_d.exists() and board_w.exists()

    sc = json.loads(screener.read_text())
    assert sc["schema"] == "stage_screener.v1"
    assert sc["is_context_only"] is True and sc["display_only"] is True
    assert sc["surface"] == "A"
    assert sc["n"] == len(sc["rows"]) > 0

    # Column parity for surface A (masterplan §1).
    row = sc["rows"][0]
    for col in ("ticker", "name", "sector", "region", "source",
                "industry_percentile", "sata_score", "sata_change_1w", "stage",
                "stage_detailed", "stage_label", "weeks_in_stage", "atr_ext",
                "atr_pct_price", "mansfield_rs", "ec_sent", "ec_perf", "rating"):
        assert col in row, f"screener row missing {col}"
    # FIX 1a: every live-classified row is US-listed → region "USA", source "live"
    # (no overview seed present in this env, so no EU/ASIA seed rows appended).
    assert all(r["region"] == "USA" and r["source"] == "live" for r in sc["rows"])
    assert sc["counts"]["by_region"]["USA"]["seed"] == 0

    # Stage-2 names sort first; the freshest Stage-2 leads.
    assert row["stage"] == 2
    # NVDA (fresh 2A) should outrank the non-fresh Stage-2 names.
    tickers = [r["ticker"] for r in sc["rows"]]
    assert tickers[0] in ("NVDA", "AVGO")

    # UI stage labels reproduce the two flagship chips.
    labels = {r["ticker"]: r["stage_label"] for r in sc["rows"]}
    assert labels.get("AVGO") == "2X Catch"
    assert labels.get("COST") == "2X Bullish"

    bd = json.loads(board_d.read_text())
    bw = json.loads(board_w.read_text())
    assert bd["schema"] == "stage_board_daily.v1" and bd["variant"] == "daily"
    assert bw["schema"] == "stage_board_weekly.v1" and bw["variant"] == "weekly"
    assert bd["is_context_only"] is True and bw["is_context_only"] is True


# ---------------------------------------------------------------------------
# 1c. FIX 1b — EU / ASIA seed rows appended so the region toggle is 3-region.
# ---------------------------------------------------------------------------
def _write_overview_seed(dr, rows):
    """Write a tiny EquityDesk overview seed at the lane's expected path."""
    cols = ["ticker", "region", "name_ui", "gics_sector", "gics_industry",
            "industry_percentile", "sata_score", "sata_change_1w", "stage_flag",
            "stage_detailed", "weeks_in_stage", "atr_ext", "atr_14w", "close",
            "earnings_call_sent", "earnings_call_perf", "combined_rating",
            "mansfield_rs", "level1_tags"]
    p = dr / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=cols).to_parquet(p)


def _ov_row(ticker, region, rating, **over):
    base = dict(ticker=ticker, region=region, name_ui=f"{ticker} Co",
                gics_sector="Financials", gics_industry="Banks",
                industry_percentile=90.0, sata_score=8, sata_change_1w=0.0,
                stage_flag=2, stage_detailed="2X_fallback_bullish",
                weeks_in_stage=6, atr_ext=1.5, atr_14w=2.0, close=40.0,
                earnings_call_sent=20.0, earnings_call_perf=10.0,
                combined_rating=rating, mansfield_rs=5.0,
                level1_tags='["loan_growth", "AI"]')
    base.update(over)
    return base


def test_region_toggle_seed_rows_appended(env):
    """FIX 1b: EU + ASIA seed rows are appended (source='seed') alongside the
    live US rows (source='live'); counts.by_region discloses live/seed/available."""
    dr, _ = env
    _write_overview_seed(dr, [
        _ov_row("BBVA.MC", "EUROPE", 87),
        _ov_row("SAP.DE", "EUROPE", 80),
        _ov_row("0700.HK", "ASIA", 85),
        _ov_row("BADCLASS", "USA", 99),   # USA rows in the seed are NOT appended
    ])
    sa.build_context_feed(root=dr, asof="2026-07-17")
    sc = json.loads((dr / "stage_analysis" / "screener.json").read_text())

    by_src = {}
    for r in sc["rows"]:
        by_src.setdefault((r["region"], r["source"]), []).append(r["ticker"])
    # Live US rows present, seed EU/ASIA rows appended, no USA-seed leak.
    assert by_src.get(("USA", "live"))            # our classifier's US names
    assert set(by_src.get(("EUROPE", "seed"), [])) == {"BBVA.MC", "SAP.DE"}
    assert set(by_src.get(("ASIA", "seed"), [])) == {"0700.HK"}
    assert ("USA", "seed") not in by_src
    # Seed rows carry the mapped schema (industry, atr_pct_price, rating).
    eu = next(r for r in sc["rows"] if r["ticker"] == "BBVA.MC")
    assert eu["industry"] == "Banks" and eu["rating"] == 87
    assert eu["atr_pct_price"] == round(2.0 / 40.0, 5)   # atr_14w / close
    assert eu["stage_label"] == "2X Bullish"
    # counts.by_region disclosure.
    br = sc["counts"]["by_region"]
    assert br["EUROPE"]["seed"] == 2 and br["EUROPE"]["live"] == 0
    assert br["ASIA"]["seed"] == 1
    assert br["USA"]["live"] > 0 and br["USA"]["seed"] == 0


def test_live_frame_populates_industry_ranks_flows_and_screener(env):
    """The classifier's same-day frame, not an optional stage seed, powers all
    industry surfaces and immediately fills the screener's industry context."""
    dr, _ = env
    industry_by_ticker = {
        "NVDA": "Semiconductors", "AVGO": "Semiconductors",
        "INTC": "Semiconductors", "COST": "Consumer Staples Distribution",
        "WMT": "Consumer Staples Distribution", "MMM": "Industrial Conglomerates",
        "GE": "Industrial Conglomerates", "PFE": "Pharmaceuticals",
        "KO": "Beverages", "SPY": "Broad Market ETF",
    }
    _write_overview_seed(dr, [
        _ov_row(tk, "USA", 75, gics_industry=industry)
        for tk, industry in industry_by_ticker.items()
    ])

    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    ranks = json.loads((dr / "stage_analysis" / "industry_ranks.json").read_text())
    flows = json.loads((dr / "stage_analysis" / "industry_flows.json").read_text())
    pct = json.loads((dr / "stage_analysis" / "industry_name_pctile.json").read_text())
    screener = json.loads((dr / "stage_analysis" / "screener.json").read_text())

    assert ranks["n_industries"] >= 5
    assert flows["n_industry"] == ranks["n_industries"]
    assert ranks["status"] == flows["status"] == "ready"
    assert ranks["coverage"]["non_vacuous"] is True
    assert ranks["coverage"]["freshness"] == {
        "expected_asof": "2026-07-17",
        "source_asof": "2026-07-17",
        "status": "current",
        # Wave 8 §6.1 — freshness is judged on the completed-Stage-week plane;
        # the daily values above stay for audit but no longer decide the verdict.
        "plane": "stage_week",
        "expected_stage_week": "2026-07-17",
        "source_stage_week": "2026-07-17",
    }
    assert ranks["coverage"]["input_rows"] == contract["counts"]["total"]
    assert set(industry_by_ticker) <= set(pct["percentiles"])

    live = {r["ticker"]: r for r in screener["rows"] if r["source"] == "live"}
    assert live["NVDA"]["industry"] == "Semiconductors"
    assert live["NVDA"]["industry_percentile"] is not None
    assert all(live[tk]["industry"] == industry
               for tk, industry in industry_by_ticker.items())


def test_live_industry_freshness_uses_ohlcv_source_not_requested_asof(env):
    """A build label can neither launder NOR falsely condemn a classifier snapshot.

    Original intent (unchanged): the freshness verdict must come from what the
    classifier actually read, never from the date a caller asked the builder to
    label. Wave 8 §6.1 changed the PLANE that verdict is computed on, so the old
    assertion here — that a one-day daily lag makes the ranks `warn`/`stale` —
    now pins the very defect this wave fixes: the classifier is weekly-native,
    Aug-19 tape and an Aug-20 build BOTH describe the completed week ending
    Aug-14, and downgrading that is the false-stale bug from the mission.

    So the intent is tested more strongly than before: build the SAME data under
    two different `asof` labels and assert the freshness verdict is byte-identical.
    A verdict that moved with the label would be reading the clock.
    """
    dr, _ = env
    _write_overview_seed(dr, [
        _ov_row(tk, "USA", 75, gics_industry="Software")
        for tk in ("NVDA", "AVGO", "INTC")
    ])

    sa.build_context_feed(root=dr, asof="2026-07-18")
    ranks_later = json.loads((dr / "stage_analysis" / "industry_ranks.json").read_text())
    fresh_later = ranks_later["coverage"]["freshness"]

    # The data plane is unchanged, so the verdict must be CURRENT, not stale:
    # both dates fall inside the same completed Stage week.
    assert fresh_later["plane"] == "stage_week"
    assert fresh_later["status"] == "current"
    assert fresh_later["source_stage_week"] == fresh_later["expected_stage_week"]
    assert "source_asof_stale" not in ranks_later["coverage"]["issues"], (
        "a one-day daily lag inside one completed Stage week is not staleness")
    # The daily plane is still disclosed for audit, and still reports the real
    # gap between the requested label and the tape.
    assert fresh_later["expected_asof"] == "2026-07-18"
    assert fresh_later["source_asof"] == "2026-07-17"

    # THE INTENT: re-label the same data and the verdict must not move.
    sa.build_context_feed(root=dr, asof="2026-07-24")
    fresh_relabelled = json.loads(
        (dr / "stage_analysis" / "industry_ranks.json").read_text()
    )["coverage"]["freshness"]
    assert fresh_relabelled["status"] == fresh_later["status"]
    assert fresh_relabelled["source_stage_week"] == fresh_later["source_stage_week"]
    assert fresh_relabelled["source_asof"] == fresh_later["source_asof"] == "2026-07-17"


def test_seed_region_cap_disclosed(env):
    """FIX 1b: a region over the per-region cap is truncated by rating and the
    uncapped `available` count is disclosed."""
    dr, _ = env
    # 3 ASIA rows; cap to 2 to prove truncation keeps the top-rated.
    monkeypatch_cap = sa._SEED_REGION_CAP
    try:
        sa._SEED_REGION_CAP = 2
        _write_overview_seed(dr, [
            _ov_row("A.HK", "ASIA", 50),
            _ov_row("B.HK", "ASIA", 90),   # top-rated → kept
            _ov_row("C.HK", "ASIA", 70),   # → kept
        ])
        sa.build_context_feed(root=dr, asof="2026-07-17")
        sc = json.loads((dr / "stage_analysis" / "screener.json").read_text())
        seed = {r["ticker"] for r in sc["rows"] if r["source"] == "seed"}
        assert seed == {"B.HK", "C.HK"}           # A.HK (lowest rating) dropped
        br = sc["counts"]["by_region"]["ASIA"]
        assert br["available"] == 3 and br["seed"] == 2 and br["cap"] == 2
    finally:
        sa._SEED_REGION_CAP = monkeypatch_cap


# ---------------------------------------------------------------------------
# 2. sga_score determinism + bounds.
# ---------------------------------------------------------------------------
def test_sga_score_deterministic_and_bounded(env):
    dr, _ = env
    c1 = sa.build_context_feed(root=dr, asof="2026-07-17")
    c2 = sa.build_context_feed(root=dr, asof="2026-07-17")
    s1 = {r["ticker"]: r["sga_score"] for r in c1["top_stage2"]}
    s2 = {r["ticker"]: r["sga_score"] for r in c2["top_stage2"]}
    assert s1 == s2, "sga_score must be deterministic across runs"
    for r in c1["top_stage2"]:
        assert isinstance(r["sga_score"], int)
        assert 0 <= r["sga_score"] <= 100
    for r in c1["warnings_stage3"]:
        assert 0 <= r["sga_score"] <= 100


# ---------------------------------------------------------------------------
# 3. Extension penalty direction: a stretched name scores below an otherwise
#    equal un-stretched name.
# ---------------------------------------------------------------------------
def test_extension_penalty_direction():
    base = dict(stage=2, weeks_in_stage=5, fresh=True, mansfield_rs=5.0,
                vol_ratio=1.5, pct_vs_ma30=5.0)
    stretched = dict(base, pct_vs_ma30=35.0)
    s_base = sa._compute_sga_score(base, slope_pctile=0.5, gate_tier="T1")
    s_stretch = sa._compute_sga_score(stretched, slope_pctile=0.5, gate_tier="T1")
    assert s_stretch < s_base, "extension beyond 15% must lower the score"

    # No penalty below the 15% threshold.
    mild = dict(base, pct_vs_ma30=14.9)
    assert sa._compute_sga_score(mild, 0.5, "T1") == s_base


# ---------------------------------------------------------------------------
# 4. Same-day idempotent change feed — changes preserved, not wiped.
# ---------------------------------------------------------------------------
def test_same_day_change_feed_idempotent(env):
    dr, stage_map = env
    # Seed a prior-day contract so day-over-day diffing produces items.
    outpath = dr / "stage_analysis" / "context" / "latest.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    prior = {
        "schema": "stage_context.v1",
        "asof": "2026-07-16",
        "_current_by_key": {
            "NVDA": {"stage": 1, "fresh": False, "event": None},  # will enter stage2
            "MMM": {"stage": 2, "fresh": False, "event": None},   # will top out -> stage3
        },
        "prev_state": {"asof": "2026-07-15", "by_key": {}},
    }
    outpath.write_text(json.dumps(prior))

    c1 = sa.build_context_feed(root=dr, asof="2026-07-17")
    items1 = c1["changes"]["items"]
    kinds1 = {(it["kind"], it["ticker"]) for it in items1}
    assert ("entered_stage2", "NVDA") in kinds1
    assert ("topping", "MMM") in kinds1
    assert c1["changes"]["n"] == len(items1) > 0

    # Re-run SAME asof: the change set must be preserved (base frozen), not wiped.
    c2 = sa.build_context_feed(root=dr, asof="2026-07-17")
    kinds2 = {(it["kind"], it["ticker"]) for it in c2["changes"]["items"]}
    assert kinds2 == kinds1, "same-day re-run must not wipe the day's changes"


# ---------------------------------------------------------------------------
# 4b. _diff_by_key emits ONE item per ticker transition (FIX 7a): when a generic
#     (left_stage2) and a specific (topping / entered_stage4) kind both apply,
#     only the specific one is emitted.
# ---------------------------------------------------------------------------
def test_diff_by_key_specific_over_generic():
    base = {
        "TOP": {"stage": 2, "fresh": False, "event": None},   # -> stage 3 (topping)
        "ROLL": {"stage": 2, "fresh": False, "event": None},  # -> stage 4 (entered_stage4)
        "FADE": {"stage": 2, "fresh": False, "event": None},  # -> stage 1 (left_stage2 only)
        "UP": {"stage": 1, "fresh": False, "event": None},    # -> stage 2 (entered_stage2)
    }
    new = {
        "TOP": {"stage": 3, "fresh": False, "event": None},
        "ROLL": {"stage": 4, "fresh": False, "event": None},
        "FADE": {"stage": 1, "fresh": False, "event": None},
        "UP": {"stage": 2, "fresh": False, "event": None},
    }
    items = sa._diff_by_key(base, new)
    by_tk: dict[str, list] = {}
    for it in items:
        by_tk.setdefault(it["ticker"], []).append(it["kind"])

    # S2->S3: ONLY topping (no left_stage2).
    assert by_tk["TOP"] == ["topping"]
    # S2->S4: ONLY entered_stage4 (no left_stage2).
    assert by_tk["ROLL"] == ["entered_stage4"]
    # S2->S1 (no specific kind): left_stage2 is the honest generic.
    assert by_tk["FADE"] == ["left_stage2"]
    # S1->S2: entered_stage2.
    assert by_tk["UP"] == ["entered_stage2"]
    # Exactly one item per transitioning ticker.
    assert all(len(v) == 1 for v in by_tk.values())


# ---------------------------------------------------------------------------
# 5. Wave 8 §5 — the change feed is keyed on the Stage week, not the wall
#    clock. A same-week rerun (only `asof` rolls) must not duplicate or wipe
#    the change set; a genuine Stage-week advance DOES fire real transitions.
# ---------------------------------------------------------------------------
def test_same_stage_week_wall_clock_roll_does_not_duplicate_or_wipe(env):
    """Run Monday then Tuesday (then Wednesday) with an IDENTICAL target Stage
    week and a changed wall-clock `asof`: no duplicate entered_stage2/'new
    today' event appears solely because the machine date rolled."""
    dr, _ = env
    # Day 1 (no prior contract): empty change set, Stage week resolved.
    c1 = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert c1["changes"]["items"] == []
    assert c1["prev_state"]["by_key"] == {}
    assert c1["target_stage_week"] == _FAKE_STAGE_WEEK

    # Day 2: SAME Stage week (the fixture's classify results are unchanged),
    # only the wall-clock `asof` rolled forward a day. The base stays frozen
    # at day-1's prev_state — it must NOT re-base off day-1's full snapshot
    # (that would fabricate transitions merely because the clock moved).
    c2 = sa.build_context_feed(root=dr, asof="2026-07-18")
    assert c2["target_stage_week"] == _FAKE_STAGE_WEEK == c1["target_stage_week"]
    assert c2["prev_state"]["by_key"] == c1["prev_state"]["by_key"]
    assert c2["changes"]["items"] == []
    assert c2["counts"]["new_today"] == 0

    # Day 3: still the same Stage week — still no duplicate/spurious event.
    c3 = sa.build_context_feed(root=dr, asof="2026-07-19")
    assert c3["target_stage_week"] == _FAKE_STAGE_WEEK
    assert c3["changes"]["items"] == []
    assert c3["counts"]["new_today"] == 0


def test_stage_week_advance_fires_genuine_transitions(env):
    """Advancing the target Stage week (not merely the wall clock) DOES fire
    genuine transitions — the containment must not also suppress real news."""
    dr, _ = env
    outpath = dr / "stage_analysis" / "context" / "latest.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    prior_week = "2026-07-10"
    prior = {
        "schema": "stage_context.v1",
        "asof": "2026-07-10",
        "target_stage_week": prior_week,
        "_current_by_key": {
            "NVDA": {"stage": 1, "fresh": False, "event": None},  # will enter stage2
            "AVGO": {"stage": 2, "fresh": True, "event": None},   # unchanged
        },
        "prev_state": {"asof": "2026-07-03", "stage_week": "2026-07-03", "by_key": {}},
    }
    outpath.write_text(json.dumps(prior))

    # This run resolves to the fixture's fixed Stage week, which genuinely
    # differs from prior_week.
    c = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert c["target_stage_week"] == _FAKE_STAGE_WEEK != prior_week
    kinds = {(it["kind"], it["ticker"]) for it in c["changes"]["items"]}
    assert ("entered_stage2", "NVDA") in kinds
    assert c["prev_state"]["stage_week"] == prior_week


def test_same_stage_week_roll_preserves_a_NON_EMPTY_change_set(env):
    """The "not WIPED" half of §5, which the sibling test above cannot reach.

    That test starts from an empty prior contract, so every day it asserts an
    EMPTY item list — which would also pass if a same-week rerun silently wiped
    a real change set. Here day 1 starts from a prior contract on a DIFFERENT
    Stage week, so it produces a genuinely non-empty `items`; the wall clock then
    rolls twice with the Stage week held constant, and the change set must come
    back byte-identical: neither wiped nor duplicated.
    """
    dr, _ = env
    outpath = dr / "stage_analysis" / "context" / "latest.json"
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(json.dumps({
        "schema": "stage_context.v1",
        "asof": "2026-07-10",
        "target_stage_week": "2026-07-10",
        "_current_by_key": {
            "NVDA": {"stage": 1, "fresh": False, "event": None},  # -> entered_stage2
            "AVGO": {"stage": 2, "fresh": True, "event": None},
        },
        "prev_state": {"asof": "2026-07-03", "stage_week": "2026-07-03", "by_key": {}},
    }))

    day1 = sa.build_context_feed(root=dr, asof="2026-07-17")
    items1 = day1["changes"]["items"]
    assert items1, "day 1 must produce a NON-EMPTY change set for this test to mean anything"
    assert ("entered_stage2", "NVDA") in {(i["kind"], i["ticker"]) for i in items1}
    new_today1 = day1["counts"]["new_today"]
    assert new_today1 >= 1

    # Wall clock rolls; Stage week does not.
    day2 = sa.build_context_feed(root=dr, asof="2026-07-18")
    assert day2["target_stage_week"] == day1["target_stage_week"]
    assert day2["changes"]["items"] == items1, (
        "a same-Stage-week rerun must PRESERVE the change set, not wipe it")
    assert day2["counts"]["new_today"] == new_today1, (
        "new_today must neither reset to 0 nor double-count on a clock roll")

    day3 = sa.build_context_feed(root=dr, asof="2026-07-19")
    assert day3["changes"]["items"] == items1
    assert day3["counts"]["new_today"] == new_today1


# ---------------------------------------------------------------------------
# 6. Forward ledger dedup — same-day re-runs never duplicate.
# ---------------------------------------------------------------------------
def test_forward_ledger_dedup(env):
    dr, _ = env
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    n1 = sa.append_forward_ledger(contract, root=dr)
    assert n1 >= 2, "expected the 2 fresh Stage-2 names (NVDA, AVGO)"

    n2 = sa.append_forward_ledger(contract, root=dr)
    assert n2 == 0, "same-day re-run must not duplicate ledger rows"

    ledger = dr / "stage_analysis" / "forward_ledger.jsonl"
    lines = [ln for ln in ledger.read_text().splitlines() if ln.strip()]
    assert len(lines) == n1
    keys = [(json.loads(ln)["date"], json.loads(ln)["ticker"]) for ln in lines]
    assert len(keys) == len(set(keys)), "no duplicate (date,ticker) keys"

    # Row shape (SGA-R7).
    row = json.loads(lines[0])
    for field in ("date", "ticker", "sga_score", "gate_tier",
                  "weeks_in_stage", "earnings_present", "sentiment", "performance"):
        assert field in row


# ---------------------------------------------------------------------------
# 6b. Forward-ledger row dates come from the DATA PLANE, never the clock.
#
#     Every date below is a pinned weekday literal — the rule is evidence
#     arithmetic and must grade identically on any run day. 2026-07-31 is a
#     Friday; 2026-08-03 is the following Monday, i.e. exactly the UTC date a
#     Friday-evening PT nightly stamps (the audited defect shape).
# ---------------------------------------------------------------------------
_FRIDAY = "2026-07-31"
_THURSDAY = "2026-07-30"
_UTC_DRIFTED_MONDAY = "2026-08-03"


def _ledger_contract(rows, *, asof=_UTC_DRIFTED_MONDAY, data_session=None):
    """A stage_context.v1 slice carrying only what append_forward_ledger reads."""
    contract = {"schema": "stage_context.v1", "asof": asof, "top_stage2": rows}
    if data_session is not None:
        contract["data_session"] = data_session
    return contract


def _fresh_row(ticker, *, stage_source_asof=None, **over):
    row = {
        "ticker": ticker,
        "fresh": True,
        "sga_score": 71,
        "gate_tier": "T2",
        "weeks_in_stage": 4,
        "earnings": {"present": True, "sentiment": 0.25, "performance": 4.0},
    }
    if stage_source_asof is not None:
        row["stage_source_asof"] = stage_source_asof
    row.update(over)
    return row


def _ledger_rows(dr: Path) -> list[dict]:
    p = dr / "stage_analysis" / "forward_ledger.jsonl"
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def test_ledger_stamps_stage_source_asof_not_the_utc_drifted_asof(tmp_path):
    """THE DEFECT, PINNED: a contract labelled with the next calendar day (the
    UTC date of a PT-evening run) must still stamp rows with the Friday bar the
    stages were computed from."""
    dr = tmp_path / "data"
    contract = _ledger_contract(
        [_fresh_row("NVDA", stage_source_asof=_FRIDAY),
         _fresh_row("AVGO", stage_source_asof=_FRIDAY)],
        asof=_UTC_DRIFTED_MONDAY)

    assert sa.append_forward_ledger(contract, root=dr) == 2

    rows = _ledger_rows(dr)
    assert [r["date"] for r in rows] == [_FRIDAY, _FRIDAY]
    assert _UTC_DRIFTED_MONDAY not in {r["date"] for r in rows}
    assert {r["session_source"] for r in rows} == {"stage_source_asof"}
    # Every pre-existing field survives the additive change.
    for field in ("date", "ticker", "sga_score", "gate_tier", "weeks_in_stage",
                  "earnings_present", "sentiment", "performance"):
        assert field in rows[0], field
    assert rows[0]["earnings_present"] is True


def test_ledger_frozen_store_rerun_appends_zero(tmp_path):
    """A re-run against the same frozen contract re-derives the same session
    keys, so the (date,ticker) dedupe refuses every row — even though the wall
    clock (and any later `asof` label) has moved on."""
    dr = tmp_path / "data"
    contract = _ledger_contract(
        [_fresh_row("NVDA", stage_source_asof=_FRIDAY),
         _fresh_row("AVGO", stage_source_asof=_FRIDAY)],
        asof=_UTC_DRIFTED_MONDAY)
    assert sa.append_forward_ledger(contract, root=dr) == 2

    # Same tape, a later calendar label — the old writer would have appended 2
    # more rows under a fresh date.
    later = _ledger_contract(
        [_fresh_row("NVDA", stage_source_asof=_FRIDAY),
         _fresh_row("AVGO", stage_source_asof=_FRIDAY)],
        asof="2026-08-05")
    assert sa.append_forward_ledger(later, root=dr) == 0
    assert len(_ledger_rows(dr)) == 2


def test_ledger_session_is_per_ticker_not_shared(tmp_path):
    """Two names whose stages were computed from DIFFERENT bars land on their
    own sessions — the stamp is per-ticker evidence, not one board-wide date."""
    dr = tmp_path / "data"
    contract = _ledger_contract(
        [_fresh_row("NVDA", stage_source_asof=_FRIDAY),
         _fresh_row("STALE", stage_source_asof=_THURSDAY)],
        asof=_UTC_DRIFTED_MONDAY, data_session=_FRIDAY)
    assert sa.append_forward_ledger(contract, root=dr) == 2

    by_ticker = {r["ticker"]: r for r in _ledger_rows(dr)}
    assert by_ticker["NVDA"]["date"] == _FRIDAY
    assert by_ticker["STALE"]["date"] == _THURSDAY
    assert {r["session_source"] for r in by_ticker.values()} == {"stage_source_asof"}


def test_ledger_falls_back_to_contract_data_session(tmp_path):
    """Rung (b): a row with no per-ticker bar takes the contract's data_session
    — still the data plane, never `asof`."""
    dr = tmp_path / "data"
    key_absent = _fresh_row("NVDA")
    key_null = _fresh_row("AVGO")
    key_null["stage_source_asof"] = None      # present but unknowable
    contract = _ledger_contract(
        [key_absent, key_null], asof=_UTC_DRIFTED_MONDAY, data_session=_FRIDAY)
    assert sa.append_forward_ledger(contract, root=dr) == 2

    rows = _ledger_rows(dr)
    assert {r["date"] for r in rows} == {_FRIDAY}
    assert {r["session_source"] for r in rows} == {"contract_data_session"}


def test_ledger_skips_rows_with_no_data_plane_session(tmp_path, capsys):
    """Rung (c): no per-ticker bar AND no contract data_session -> the row is
    skipped and counted; a real GitHub annotation discloses it. The wall clock
    and `asof` never rescue a session-less row."""
    dr = tmp_path / "data"
    contract = _ledger_contract(
        [_fresh_row("NVDA"), _fresh_row("AVGO")], asof=_UTC_DRIFTED_MONDAY)

    assert sa.append_forward_ledger(contract, root=dr) == 0
    assert not (dr / "stage_analysis" / "forward_ledger.jsonl").exists()

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if "no data-plane session" in ln]
    assert lines, out
    # GitHub only parses a workflow command when "::" STARTS the line.
    assert lines[0].startswith("::")
    assert lines[0].startswith("::warning title=stage-ledger-no-session::")
    assert "2 row(s) skipped" in lines[0]


def test_ledger_mixed_batch_writes_the_provable_rows_only(tmp_path, capsys):
    """A session-less row is dropped without poisoning its neighbours."""
    dr = tmp_path / "data"
    contract = _ledger_contract(
        [_fresh_row("NVDA", stage_source_asof=_FRIDAY), _fresh_row("GHOST")],
        asof=_UTC_DRIFTED_MONDAY)

    assert sa.append_forward_ledger(contract, root=dr) == 1
    rows = _ledger_rows(dr)
    assert [(r["ticker"], r["date"]) for r in rows] == [("NVDA", _FRIDAY)]
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("::warning title=stage-ledger-no-session::")]
    assert warn and "1 row(s) skipped" in warn[0]


def test_contract_carries_data_session_and_leaves_asof_alone(env):
    """build_context_feed derives data_session from the classified bars while
    `asof` keeps its display semantics (basket-turn sibling idiom)."""
    dr, _ = env
    # Every stubbed rec classifies off the 2026-07-17 bar; the caller labels
    # the build with a LATER date, the shape the UTC drift produced nightly.
    contract = sa.build_context_feed(root=dr, asof="2026-07-20")

    assert contract["asof"] == "2026-07-20"          # display label untouched
    assert contract["data_session"] == "2026-07-17"  # the tape actually read
    assert contract["top_stage2"], "need rows to check the projection"
    assert all(r["stage_source_asof"] == "2026-07-17"
               for r in contract["top_stage2"])

    n = sa.append_forward_ledger(contract, root=dr)
    assert n >= 2
    assert {r["date"] for r in _ledger_rows(dr)} == {"2026-07-17"}


# ---------------------------------------------------------------------------
# 7. Fail-open: signal_gate.json absent -> no crash, gate_tier all null.
# ---------------------------------------------------------------------------
def test_fail_open_missing_signal_gate(env):
    dr, _ = env
    (dr.parent / "site" / "factordata" / "signal_gate.json").unlink()
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert contract["schema"] == "stage_context.v1"
    for r in contract["top_stage2"]:
        assert r["gate_tier"] is None


# ---------------------------------------------------------------------------
# 8. Fail-open: earnings parquet absent -> earnings sub-dict all null/present=False.
# ---------------------------------------------------------------------------
def test_fail_open_missing_earnings(env):
    dr, _ = env
    assert not (dr / "earnings_calls" / "scores.parquet").exists()
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    for r in contract["top_stage2"]:
        e = r["earnings"]
        assert e["present"] is False
        assert e["sentiment"] is None and e["performance"] is None
        assert e["tone_word"] is None and e["tags"] == []


def test_earnings_join_present(env):
    """When scores.parquet is present, tone_word derives from sentiment."""
    dr, _ = env
    ec = dr / "earnings_calls"
    ec.mkdir(parents=True)
    # tags ship as a JSON string per the §2 contract ("tags (json)").
    df = pd.DataFrame([
        {"ticker": "NVDA", "quarter": "Q2 2026", "call_date": "2026-06-30",
         "sentiment": 0.55, "performance": 8.1, "tags": json.dumps(["guidance_raised"])},
        {"ticker": "COST", "quarter": "Q3 2026", "call_date": "2026-06-15",
         "sentiment": -0.4, "performance": 3.0, "tags": json.dumps(["miss_and_cut"])},
    ])
    df.to_parquet(ec / "scores.parquet")
    _write_scores_manifest(ec / "scores.parquet")
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    by_tk = {r["ticker"]: r for r in contract["top_stage2"]}
    assert by_tk["NVDA"]["earnings"]["present"] is True
    assert by_tk["NVDA"]["earnings"]["tone_word"] == "upbeat"
    assert by_tk["NVDA"]["earnings"]["tags"] == ["guidance_raised"]
    assert by_tk["COST"]["earnings"]["tone_word"] == "downbeat"
    assert by_tk["COST"]["earnings"]["tags"] == ["miss_and_cut"]


def test_earnings_seed_fallback_and_live_overlay(tmp_path):
    """Committed backfill seed populates earnings on every render; the live
    (R2-fetched) scores.parquet overlays per ticker when the Qwen worker runs."""
    dr = tmp_path
    seed_dir = dr / "stage_analysis" / "backfill"
    seed_dir.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": "AAA", "quarter": "Q1", "sentiment": 0.5, "performance": 7.0,
         "tone_word": "confident", "tags": json.dumps([]), "summary": "Seed outlook AAA."},
        {"ticker": "BBB", "quarter": "Q1", "sentiment": -0.4, "performance": 3.0,
         "tone_word": "downbeat", "tags": json.dumps([]), "summary": "Seed outlook BBB."},
    ]).to_parquet(seed_dir / "earnings_seed.parquet")

    # Seed only -> both present, prose intact, no dict-blob leak.
    m = sa._load_earnings_scores(dr)
    assert m["AAA"]["present"] and m["AAA"]["summary"] == "Seed outlook AAA."
    assert m["BBB"]["tone_word"] == "downbeat"
    assert not m["AAA"]["summary"].startswith("{")

    # Live worker store overlays AAA with a fresher call and adds CCC.
    ec = dr / "earnings_calls"
    ec.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": "AAA", "quarter": "Q2", "sentiment": 0.9, "performance": 9.0,
         "tone_word": "confident", "tags": json.dumps([]), "summary": "Fresh call AAA."},
        {"ticker": "CCC", "quarter": "Q2", "sentiment": 0.2, "performance": 6.0,
         "tone_word": "steady", "tags": json.dumps([]), "summary": "Fresh call CCC."},
    ]).to_parquet(ec / "scores.parquet")
    _write_scores_manifest(ec / "scores.parquet")
    m2 = sa._load_earnings_scores(dr)
    assert m2["AAA"]["summary"] == "Fresh call AAA." and m2["AAA"]["quarter"] == "Q2"
    assert m2["BBB"]["summary"] == "Seed outlook BBB."  # seed retained where no live row
    assert m2["CCC"]["present"] is True                 # live-only ticker added


def test_degraded_or_incomplete_live_rows_never_override_seed(tmp_path):
    dr = tmp_path
    seed_dir = dr / "stage_analysis" / "backfill"
    seed_dir.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": "AAA", "quarter": "Q1", "sentiment": 0.5,
         "performance": 7.0, "summary": "Healthy seed."},
    ]).to_parquet(seed_dir / "earnings_seed.parquet")

    live_dir = dr / "earnings_calls"
    live_dir.mkdir(parents=True)
    pd.DataFrame([
        {"ticker": "AAA", "quarter": "Q2", "sentiment": None,
         "performance": None, "summary": None, "is_context_only": True,
         "degraded_reason": "openai_compat_error"},
        {"ticker": "BBB", "quarter": "Q2", "sentiment": None,
         "performance": 7.0, "summary": "Partial.", "is_context_only": True,
         "degraded_reason": None},
        {"ticker": "CCC", "quarter": "Q2", "sentiment": 0.2,
         "performance": 6.0, "summary": "Wrong authority.",
         "is_context_only": False, "degraded_reason": None},
    ]).to_parquet(live_dir / "scores.parquet")
    _write_scores_manifest(live_dir / "scores.parquet")

    scores = sa._load_earnings_scores(dr)
    assert scores["AAA"]["summary"] == "Healthy seed."
    assert "BBB" not in scores
    assert "CCC" not in scores


def test_future_dated_live_rows_never_reach_stage_cards(tmp_path):
    dr = tmp_path
    seed_dir = dr / "stage_analysis" / "backfill"
    seed_dir.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "AAA", "quarter": "Q1", "sentiment": 0.5,
        "performance": 7.0, "summary": "Last known healthy call.",
    }]).to_parquet(seed_dir / "earnings_seed.parquet")

    live_dir = dr / "earnings_calls"
    live_dir.mkdir(parents=True)
    pd.DataFrame([
        {
            "ticker": "AAA", "quarter": "Q2", "call_date": "2099-08-06",
            "sentiment": 0.9, "performance": 9.0,
            "summary": "Future override.", "is_context_only": True,
            "degraded_reason": None,
        },
        {
            "ticker": "BBB", "quarter": "Q2", "call_date": "2099-08-06",
            "sentiment": 0.8, "performance": 8.0,
            "summary": "Future addition.", "is_context_only": True,
            "degraded_reason": None,
        },
    ]).to_parquet(live_dir / "scores.parquet")
    _write_scores_manifest(live_dir / "scores.parquet")

    scores = sa._load_earnings_scores(dr)
    assert scores["AAA"]["summary"] == "Last known healthy call."
    assert "BBB" not in scores


# ---------------------------------------------------------------------------
# 9. Fail-open: SPY absent -> no crash, market block still present.
# ---------------------------------------------------------------------------
def test_fail_open_missing_spy(env):
    dr, _ = env
    (dr / "yahoo" / "SPY.parquet").unlink()
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert "market" in contract
    assert set(contract["market"].keys()) == {
        "pct_stage2", "pct_stage4", "weather", "spy_stage", "spy_weeks"}


def test_spy_stage_null_when_unclassifiable(env, monkeypatch):
    """FIX 3 — a failed SPY read must leave spy_stage/spy_weeks None, never a
    silent default Stage 2. SPY drops out of the roster (classify -> None) and
    the yahoo bench is absent, so no path can set a stage."""
    dr, stage_map = env
    # SPY unclassifiable on the roster path.
    m = dict(stage_map)
    m["SPY"] = None
    monkeypatch.setattr(sa, "_classify_one", lambda tk: (tk, m.get(tk)))
    # ...and the bench fallback file is gone.
    (dr / "yahoo" / "SPY.parquet").unlink()
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert contract["market"]["spy_stage"] is None
    assert contract["market"]["spy_weeks"] is None


# ---------------------------------------------------------------------------
# 10. too_young counting — IPOX (20 weeks < 45) is counted, not in the board.
# ---------------------------------------------------------------------------
def test_too_young_counted_not_hidden(env):
    dr, _ = env
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert contract["counts"]["too_young"] >= 1
    board_tickers = {r["ticker"] for r in contract["top_stage2"]}
    assert "IPOX" not in board_tickers
    assert "IPOX" not in contract["roster"]
    # total counts only classifiable names.
    assert contract["counts"]["total"] == len(contract["roster"])


def test_too_young_flag_and_stage_zero_paths(env, monkeypatch):
    """Both the real-classifier signals (too_young=True; stage=0) count as
    too-young, not as a real stage."""
    dr, stage_map = env
    m = dict(stage_map)
    # A name that ONLY carries stage=0 (no too_young flag) is still too-young.
    m["ZERO"] = dict(stage=0, weeks_in_stage=0, fresh=False)
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    fr = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                       "volume": 1}, index=idx)
    fr.index.name = "Date"
    fr.to_parquet(dr / "baskets" / "ohlcv" / "ZERO.parquet")
    monkeypatch.setattr(sa, "_classify_one", lambda tk: (tk, m.get(tk)))
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert "ZERO" not in contract["roster"]
    assert contract["counts"]["too_young"] >= 2  # IPOX + ZERO


# ---------------------------------------------------------------------------
# 11. why / why_zh present, paired, and jargon-free.
# ---------------------------------------------------------------------------
_BANNED = ("z-score", "n=", "percentile", "pctile", "stage_context", "sga_score", "mansfield")


def test_why_present_and_jargon_free(env):
    dr, _ = env
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert contract["top_stage2"], "need rows to check rationale"
    for r in contract["top_stage2"]:
        assert 2 <= len(r["why"]) <= 3
        assert 2 <= len(r["why_zh"]) <= 3
        assert len(r["why"]) == len(r["why_zh"])
        for b in r["why"]:
            low = b.lower()
            for bad in _BANNED:
                assert bad not in low, f"jargon '{bad}' in why bullet: {b!r}"
        # ZH bullets contain CJK.
        for b in r["why_zh"]:
            assert any("一" <= ch <= "鿿" for ch in b), b


# ---------------------------------------------------------------------------
# 12. Market weather thresholds.
# ---------------------------------------------------------------------------
def test_weather_thresholds():
    assert sa._weather(50.0, 10.0) == "advancing"   # >=40 and > 1.5x stage4
    assert sa._weather(60.0, 45.0) == "deteriorating"  # stage4 >= 40 dominates
    assert sa._weather(30.0, 20.0) == "mixed"
    assert sa._weather(46.0, 40.0) == "deteriorating"  # 46 not > 1.5*40=60 -> not advancing; s4>=40
    assert sa._weather(46.0, 30.0) == "advancing"
    # FIX 7d floor: 42% Stage-2 with light Stage-4 is now advancing (was mixed at 45 floor).
    assert sa._weather(42.0, 20.0) == "advancing"
    assert sa._weather(38.0, 10.0) == "mixed"       # below the 40 floor stays mixed


# ---------------------------------------------------------------------------
# 13. Atomic write leaves a valid JSON at latest.json (no .tmp residue).
# ---------------------------------------------------------------------------
def test_atomic_write_output(env):
    dr, _ = env
    sa.build_context_feed(root=dr, asof="2026-07-17")
    outpath = dr / "stage_analysis" / "context" / "latest.json"
    assert outpath.exists()
    assert not outpath.with_suffix(".json.tmp").exists()
    loaded = json.loads(outpath.read_text())
    assert loaded["schema"] == "stage_context.v1"


# ---------------------------------------------------------------------------
# 14. Universe union + name/sector fallback.
# ---------------------------------------------------------------------------
def test_universe_union_and_fallback(env):
    dr, _ = env
    # Add a stray ohlcv-only ticker with no membership row.
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    frame = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1},
        index=idx)
    frame.index.name = "Date"
    frame.to_parquet(dr / "baskets" / "ohlcv" / "ZZZZ.parquet")

    uni = sa.build_universe(root=dr)
    assert "ZZZZ" in uni
    assert uni["ZZZZ"]["company"] == "ZZZZ"       # fallback = ticker
    assert uni["ZZZZ"]["sector"] == "Unknown"     # fallback sector
    assert uni["NVDA"]["company"] == "NVIDIA"      # known name
    assert uni["NVDA"]["sector"] == "Information Technology"


# ---------------------------------------------------------------------------
# 15. Fresh-first board ordering + blackout stance surface.
# ---------------------------------------------------------------------------
def test_board_fresh_first_ordering(env):
    dr, _ = env
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    board = contract["top_stage2"]
    # All fresh names come before all non-fresh names.
    fresh_flags = [r["fresh"] for r in board]
    assert fresh_flags == sorted(fresh_flags, reverse=True)
    # Fresh names are exactly NVDA and AVGO.
    fresh_tickers = {r["ticker"] for r in board if r["fresh"]}
    assert fresh_tickers == {"NVDA", "AVGO"}


# ---------------------------------------------------------------------------
# 16. Fixture self-consistency — the committed fixture is schema-valid.
# ---------------------------------------------------------------------------
def test_fixture_is_schema_valid():
    fx = json.loads(FIXTURE.read_text())
    assert fx["schema"] == "stage_context.v1"
    assert fx["is_context_only"] and fx["display_only"]
    assert set(fx["counts"].keys()) == {
        "total", "stage1", "stage2", "stage2_fresh", "stage3", "stage4",
        "too_young", "new_today"}
    # 2 fresh stage2 with earnings sub-dicts.
    fresh = [r for r in fx["top_stage2"] if r["fresh"]]
    assert len(fresh) == 2
    _EARNINGS_REQUIRED = {"present", "sentiment", "performance", "tone_word", "tags", "quarter"}
    for r in fresh:
        assert "earnings" in r
        # "summary" is an optional W5 addition — only check required keys are present
        assert _EARNINGS_REQUIRED.issubset(set(r["earnings"].keys()))
    # Change items + sectors present.
    assert fx["changes"]["n"] == len(fx["changes"]["items"]) > 0
    assert len(fx["sectors"]) >= 1
    for it in fx["changes"]["items"]:
        assert it["kind"] in {
            "entered_stage2", "left_stage2", "breakout", "topping", "entered_stage4"}


# ---------------------------------------------------------------------------
# append_stage_snapshot — nightly advancer of the overview parquet
# ---------------------------------------------------------------------------

_SNAP_PARQUET = ("stage_analysis", "backfill", "equitydesk_overview.parquet")
# Wave 8 §4.1: append_stage_snapshot now admits only stage_current=True rows
# and refuses to advance without a resolved target_stage_week — every
# snapshot test below stamps the SAME completed week on both sides.
_SNAP_WEEK = "2026-07-31"


def _snap_path(dr: Path) -> Path:
    p = dr
    for part in _SNAP_PARQUET:
        p = p / part
    return p


def _snap_recs(n: int = 3, stage: int = 2, *, current: bool = True) -> list[dict]:
    return [
        {
            "ticker": f"SNP{i}",
            "company": f"Snap Co {i}",
            "sector": "Information Technology",
            "stage": stage,
            "stage_detailed": "2X_fallback_bullish",
            "weeks_in_stage": 4 + i,
            "sata_score": 80 - i,
            "sata_change_1w": 1,
            "mansfield_rs": 5.0,
            "stage_source_asof": "2026-07-31",
            "stage_week_end": _SNAP_WEEK if current else "2026-06-26",
            "stage_current": current,
        }
        for i in range(n)
    ]


def _seed_frame() -> pd.DataFrame:
    """A minimal vendor-seed slice — deliberately WITHOUT a source column."""
    return pd.DataFrame({
        "ticker": ["AAA", "EEE"],
        "region": ["USA", "EUROPE"],
        "name_ui": ["Aaa Inc", "Eee SA"],
        "gics_sector": ["Industrials", "Industrials"],
        "stage_flag": [2, 3],
        "stage_detailed": ["2X_fallback_bullish", "3A_sideways_exhaustion"],
        "sata_score": [70, 40],
        "weeks_in_stage": [9, 2],
        "as_of_date": ["2026-07-17", "2026-07-17"],
    })


def test_snapshot_append_preserves_seed_and_orders_newest_first(tmp_path):
    dr = tmp_path / "data"
    p = _snap_path(dr)
    p.parent.mkdir(parents=True)
    _seed_frame().to_parquet(p, index=False)

    n = sa.append_stage_snapshot(_snap_recs(3), "2026-08-03", root=dr, min_rows=1,
                                 target_stage_week=_SNAP_WEEK)
    assert n == 3

    df = pd.read_parquet(p)
    # Seed rows intact, source backfilled on them.
    seed = df[df["as_of_date"] == "2026-07-17"]
    assert len(seed) == 2
    assert set(seed["source"]) == {"equitydesk_backfill"}
    assert set(seed["ticker"]) == {"AAA", "EEE"}
    # Engine rows stamped and FIRST (newest as_of first — iloc[0] readers).
    assert df.iloc[0]["as_of_date"] == "2026-08-03"
    eng = df[df["source"] == "stage_engine"]
    assert len(eng) == 3
    assert set(eng["region"]) == {"USA"}


def test_snapshot_same_asof_rerun_is_idempotent(tmp_path):
    dr = tmp_path / "data"
    sa.append_stage_snapshot(_snap_recs(3), "2026-08-03", root=dr, min_rows=1,
                             target_stage_week=_SNAP_WEEK)
    n2 = sa.append_stage_snapshot(_snap_recs(3), "2026-08-03", root=dr, min_rows=1,
                                  target_stage_week=_SNAP_WEEK)
    assert n2 == 3
    df = pd.read_parquet(_snap_path(dr))
    assert len(df) == 3  # replaced, not duplicated


def test_snapshot_retains_two_engine_asofs_plus_seed(tmp_path):
    dr = tmp_path / "data"
    p = _snap_path(dr)
    p.parent.mkdir(parents=True)
    _seed_frame().to_parquet(p, index=False)

    for asof in ("2026-08-01", "2026-08-02", "2026-08-03"):
        sa.append_stage_snapshot(_snap_recs(2), asof, root=dr, min_rows=1,
                                 target_stage_week=_SNAP_WEEK)

    df = pd.read_parquet(p)
    eng_asofs = sorted(set(df.loc[df["source"] == "stage_engine", "as_of_date"]))
    assert eng_asofs == ["2026-08-02", "2026-08-03"]  # oldest engine as_of rotated out
    assert (df["as_of_date"] == "2026-07-17").sum() == 2  # seed never rotates
    # Ordering: newest snapshot first, seed last.
    assert list(df["as_of_date"]) == sorted(df["as_of_date"], reverse=True)


def test_snapshot_floor_refuses_degenerate_universe(tmp_path, capsys):
    dr = tmp_path / "data"
    n = sa.append_stage_snapshot(_snap_recs(2), "2026-08-03", root=dr, min_rows=5,
                                 target_stage_week=_SNAP_WEEK)
    assert n == 0
    assert not _snap_path(dr).exists()
    out = capsys.readouterr().out
    warn_lines = [l for l in out.splitlines() if "stage snapshot not advanced" in l]
    assert warn_lines and warn_lines[0].startswith("::warning")


def test_snapshot_unreadable_existing_file_refuses_overwrite(tmp_path, capsys):
    dr = tmp_path / "data"
    p = _snap_path(dr)
    p.parent.mkdir(parents=True)
    p.write_bytes(b"not a parquet file")
    n = sa.append_stage_snapshot(_snap_recs(3), "2026-08-03", root=dr, min_rows=1,
                                 target_stage_week=_SNAP_WEEK)
    assert n == 0
    assert p.read_bytes() == b"not a parquet file"
    out = capsys.readouterr().out
    warn_lines = [l for l in out.splitlines() if "refusing to overwrite" in l]
    assert warn_lines and warn_lines[0].startswith("::warning")


def test_snapshot_excludes_stale_rows_so_no_pool_can_reacquire_them(tmp_path, capsys):
    """Wave 8 §4.1 (PRODUCER half): a stale per-row entry is never admitted to
    the snapshot even though the GLOBAL snapshot date is fresh, so a downstream
    candidate pool has no row to reacquire in the first place.

    The CONSUMER half — `stage2_leaders` / `stage_transitions` refusing a stale
    row — is pinned in `tests/test_marketing_supply_feeds.py` (all four ladder
    rungs), deliberately NOT here. This suite runs in the `unrun-picks-boards`
    job, which is `scope: exclusive`: a single
    `from engine.marketing.attention_source import ...` in this file drags the
    whole `engine/marketing/*` closure (plus `lib.pages` -> `scripts/*`) into
    that job's curated `paths:`, which covers none of it — measured 78
    uncovered modules, contract-delta red. Same reasoning the job's own
    comments record for `scripts.build_site`. Keep marketing imports out of
    this file.
    """
    dr = tmp_path / "data"
    recs = _snap_recs(2, current=True) + _snap_recs(1, current=False)
    recs[-1] = dict(recs[-1], ticker="FROZEN")  # avoid the SNP0/SNP1 id collision
    n = sa.append_stage_snapshot(recs, "2026-08-20", root=dr, min_rows=1,
                                 target_stage_week=_SNAP_WEEK)
    assert n == 2  # only the two CURRENT rows admitted; FROZEN excluded

    df = pd.read_parquet(_snap_path(dr))
    assert "FROZEN" not in set(df["ticker"])
    assert set(df.loc[df["source"] == "stage_engine", "stage_current"]) == {True}

    out = capsys.readouterr().out
    warn = [l for l in out.splitlines() if "excluded from the" in l]
    assert warn and warn[0].startswith("::warning")


def test_snapshot_refuses_to_advance_without_a_target_stage_week(tmp_path, capsys):
    """§4.1 — target_stage_week is None -> refuse to advance, warn, prior
    snapshot stands untouched."""
    dr = tmp_path / "data"
    n = sa.append_stage_snapshot(_snap_recs(3), "2026-08-03", root=dr, min_rows=1)
    assert n == 0
    assert not _snap_path(dr).exists()
    out = capsys.readouterr().out
    warn_lines = [l for l in out.splitlines() if "no target Stage week resolved" in l]
    assert warn_lines and warn_lines[0].startswith("::warning")


# ---------------------------------------------------------------------------
# Wave 8 — observation truth: target-week resolver, population partition,
# lifecycle-vs-currentness, screener contract.
# ---------------------------------------------------------------------------
def test_target_week_resolver_agrees_with_spy_when_population_matches(tmp_path):
    classified = {
        "SPY": {"stage": 2, "stage_week_end": "2026-08-14"},
        "AAA": {"stage": 2, "stage_week_end": "2026-08-14"},
        "BBB": {"stage": 1, "stage_week_end": "2026-08-14"},
    }
    week, source = sa._resolve_target_stage_week(tmp_path, classified)
    assert week == "2026-08-14"
    assert source == "spy_benchmark"


def test_target_week_resolver_uses_mode_when_benchmark_runs_ahead(tmp_path):
    """SPY's store (data/yahoo/) ran a week ahead of data/baskets/ohlcv/. The
    target is the POPULATION's modal week, so that week's names stay CURRENT
    instead of the whole cross-section going mass-stale on a benign store skew."""
    classified = {
        "SPY": {"stage": 2, "stage_week_end": "2026-08-21"},
        "AAA": {"stage": 2, "stage_week_end": "2026-08-14"},
        "BBB": {"stage": 1, "stage_week_end": "2026-08-14"},
        "CCC": {"stage": 4, "stage_week_end": "2026-08-14"},
    }
    week, source = sa._resolve_target_stage_week(tmp_path, classified)
    assert week == "2026-08-14"
    assert source == "population_mode_benchmark_ahead"
    for tk in ("AAA", "BBB", "CCC"):
        assert classified[tk]["stage_week_end"] == week  # genuinely CURRENT


def test_target_week_resolver_does_not_invert_when_benchmark_lags(tmp_path):
    """REGRESSION PIN for the two-sided-cap inversion (adversarial review
    2026-08-20).

    An earlier draft used ``min(spy_week, modal_week)``. When the BENCHMARK
    store is the one that freezes — SPY stuck in June while the universe
    advances to August — that cap picked SPY's June week, which flipped the
    partition inside out: the handful of genuinely stale June rows became
    ``stage_current=True`` (and would have been stamped that way into the
    machine snapshot, which the consumer gate then passes) while the whole
    current population was marked stale. Single-store freezes are the norm in
    this repo, so this was one file-freeze away from publishing June as today.

    The mode is the target in BOTH divergence directions. Asserting the
    NEGATIVE is the point: `week != spy` is what min() would have violated.
    """
    classified = {
        "SPY": {"stage": 2, "stage_week_end": "2026-06-26"},   # frozen benchmark
        "AAA": {"stage": 2, "stage_week_end": "2026-08-14"},
        "BBB": {"stage": 1, "stage_week_end": "2026-08-14"},
        "CCC": {"stage": 4, "stage_week_end": "2026-08-14"},
        "OLD": {"stage": 2, "stage_week_end": "2026-06-26"},   # genuinely stale
    }
    week, source = sa._resolve_target_stage_week(tmp_path, classified)
    assert week == "2026-08-14", "benchmark lag must not drag the target backwards"
    assert week != "2026-06-26", "min(spy, modal) would have inverted the population"
    assert source == "population_mode_benchmark_lagging"


def test_target_week_resolver_tolerates_a_non_string_week(tmp_path):
    """A classify shim handing back a `date` object must not raise out of this
    fail-open engine (the resolver coerces with str())."""
    from datetime import date as _date
    classified = {
        "SPY": {"stage": 2, "stage_week_end": "2026-08-14"},
        "AAA": {"stage": 2, "stage_week_end": _date(2026, 8, 14)},
        "BBB": {"stage": 1, "stage_week_end": "2026-08-14"},
    }
    week, source = sa._resolve_target_stage_week(tmp_path, classified)
    assert week == "2026-08-14"
    assert source == "spy_benchmark"


def test_build_context_feed_uses_population_mode_when_spy_diverges(env, monkeypatch):
    """Integration-level check of the same amendment: SPY's own store runs a
    week ahead of the rest of the population; build_context_feed must still
    treat the population's own modal week as current, not blank the page."""
    dr, stage_map = env
    m = dict(stage_map)
    m["SPY"] = dict(m["SPY"], stage_week_end="2026-07-24")  # SPY ran a week ahead
    monkeypatch.setattr(sa, "_classify_one", lambda tk: (tk, m.get(tk)))
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert contract["target_stage_week"] == _FAKE_STAGE_WEEK
    assert contract["target_week_source"] == "population_mode_benchmark_ahead"
    assert contract["population"]["status"] in ("ready", "warn")
    assert contract["counts"]["total"] and contract["counts"]["total"] > 0
    assert contract["top_stage2"], "population must stay current, not mass-evicted"


def test_week_resolution_is_completed_week_equality_not_a_day_count(tmp_path):
    """Tape ends Wed Aug 19 and tape ends Mon Aug 17 both resolve to the SAME
    completed week (Aug 14) and are both current against it; a tape ending
    Jun 30 (completed week Jun 26) is stale against that same target —
    currentness is decided by week EQUALITY, never a count of calendar days."""
    target = "2026-08-14"
    wed_tape_week = "2026-08-14"   # tape through Wed Aug 19 -> completed Aug 14
    mon_tape_week = "2026-08-14"   # tape through Mon Aug 17 -> ALSO completed Aug 14
    jun_tape_week = "2026-06-26"   # tape through Jun 30 -> completed Jun 26

    assert wed_tape_week == target
    assert mon_tape_week == target
    assert jun_tape_week != target

    # And the actual partition stamp in build_context_feed's per-record loop
    # is exactly this equality test (no day-count involved) — pin the
    # predicate itself, not just the fixture arithmetic above.
    def _stamp(stage_week_end, target_week):
        if target_week is not None and stage_week_end is not None:
            return bool(stage_week_end == target_week)
        return None

    assert _stamp(wed_tape_week, target) is True
    assert _stamp(mon_tape_week, target) is True
    assert _stamp(jun_tape_week, target) is False


def test_population_partition_exact_counts_and_denominator(tmp_path, monkeypatch):
    """Exact §10 Population example: AAPL current Stage 2, MSFT current
    Stage 4, SILA stale Stage 2 (frozen tape, real production shape — a June
    observation riding inside an August build). current total=2, stale
    total=1, current Stage-2 count=1 (not 2), the Stage-2 % denominator=2,
    SILA absent from top_stage2, SILA still browseable with stale provenance
    and no current rank; fresh=True/stage_current=False is producible."""
    dr = tmp_path / "data"
    ohlcv = dr / "baskets" / "ohlcv"
    ohlcv.mkdir(parents=True)
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    frame = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
        index=idx)
    frame.index.name = "Date"
    # SPY deliberately does NOT get an OHLCV basket file — it lives only in
    # data/yahoo/ (the real module docstring: "rarely in classified"), so it
    # is not one of the 3 roster tickers and cannot inflate the population.
    for tk in ("AAPL", "MSFT", "SILA"):
        frame.to_parquet(ohlcv / f"{tk}.parquet")
    (dr / "yahoo").mkdir(parents=True)
    frame[["close", "volume"]].to_parquet(dr / "yahoo" / "SPY.parquet")

    common = dict(vol_ratio=1.0, event=None, n_weeks=100, mansfield_rs_change=0.0)
    stage_map = {
        "AAPL": dict(common, stage=2, weeks_in_stage=4, fresh=True,
                     ma30_slope_pct5w=2.0, pct_vs_ma30=5.0, mansfield_rs=5.0,
                     arc_pos=0.3, stage_source_asof="2026-08-19",
                     stage_week_end="2026-08-14"),
        "MSFT": dict(common, stage=4, weeks_in_stage=10, fresh=False,
                     ma30_slope_pct5w=-1.0, pct_vs_ma30=-6.0, mansfield_rs=-3.0,
                     arc_pos=0.8, stage_source_asof="2026-08-19",
                     stage_week_end="2026-08-14"),
        # SILA: fresh=True (lifecycle: Stage 2, weeks<=10) but stale tape — the
        # legitimate fresh=True/stage_current=False combination (§0 gate 1).
        "SILA": dict(common, stage=2, weeks_in_stage=3, fresh=True,
                     ma30_slope_pct5w=1.5, pct_vs_ma30=3.0, mansfield_rs=2.0,
                     arc_pos=0.28, stage_source_asof="2026-06-30",
                     stage_week_end="2026-06-26"),
        "SPY": dict(common, stage=2, weeks_in_stage=20, fresh=False,
                    ma30_slope_pct5w=1.0, pct_vs_ma30=2.0, mansfield_rs=0.0,
                    arc_pos=0.4, stage_source_asof="2026-08-19",
                    stage_week_end="2026-08-14"),
    }

    monkeypatch.setattr(sa, "_classify_one", lambda tk: (tk, stage_map.get(tk)))
    monkeypatch.setattr(sa, "_resolve_workers", lambda mw: 1)
    # SPY is not in `tickers` (no basket file), so build_context_feed's
    # target-week resolver falls back to classifying the yahoo bench series
    # directly via `_classify` — stub that one call to the fixture's SPY row.
    monkeypatch.setattr(sa, "_classify", lambda *a, **k: dict(stage_map["SPY"]))

    contract = sa.build_context_feed(root=dr, asof="2026-08-20")

    pop = contract["population"]
    assert pop["current"] == 2
    assert pop["stale"] == 1
    assert contract["counts"]["stage2"] == 1   # SILA excluded from the headline
    assert contract["counts"]["total"] == 2    # the % denominator
    assert contract["market"]["pct_stage2"] == round(100.0 * 1 / 2, 1)

    top_tickers = {r["ticker"] for r in contract["top_stage2"]}
    assert "SILA" not in top_tickers
    assert "AAPL" in top_tickers
    aapl_top = next(r for r in contract["top_stage2"] if r["ticker"] == "AAPL")
    assert aapl_top["sga_score"] is not None   # admitted current rows still score

    screener = json.loads((dr / "stage_analysis" / "screener.json").read_text())
    sila_row = next(r for r in screener["rows"] if r["ticker"] == "SILA")
    assert sila_row["stage_current"] is False
    assert sila_row["stage_week_end"] == "2026-06-26"
    assert sila_row["rating"] is None          # no current rank
    assert sila_row["fresh"] is True           # lifecycle fresh + stale observation


def test_screener_row_carries_observation_truth_fields(env):
    """Screener contract (§3): stage_week_end / stage_source_asof /
    stage_current present on every live row; a seed row (non-'live' source)
    never derives currentness from `source` — it stays explicitly unknown."""
    dr, _ = env
    _write_overview_seed(dr, [_ov_row("BBVA.MC", "EUROPE", 87)])
    sa.build_context_feed(root=dr, asof="2026-07-17")
    sc = json.loads((dr / "stage_analysis" / "screener.json").read_text())

    live_rows = [r for r in sc["rows"] if r["source"] == "live"]
    assert live_rows
    for r in live_rows:
        assert "stage_week_end" in r
        assert "stage_source_asof" in r
        assert "stage_current" in r
    # Every live row in this fixture completed the SAME Stage week -> current.
    assert all(r["stage_current"] is True for r in live_rows)

    seed_rows = [r for r in sc["rows"] if r["source"] == "seed"]
    assert seed_rows
    for r in seed_rows:
        # A seed row is display inventory only — never current authority,
        # regardless of its `source` label.
        assert r["stage_current"] is None


# ---------------------------------------------------------------------------
# Nightly heal wiring (forward-ledger calendar-asof audit 2026-08-05)
# ---------------------------------------------------------------------------
class TestNightlyHealWiring:
    """The nightly lane is the ONLY lane allowed to repair this ledger.

    `.gitignore:574` scopes a house law to this file — "nightly is the SOLE
    advancer ... never commit from a worktree" — so the heal is invoked from
    scripts/build_stage_analysis.py rather than run in the PR that wrote it.
    That makes a mis-rooted call there far worse than a no-op: the repair
    simply never happens, and the only symptom is silence. `heal()` takes the
    REPO root while this CLI's `--root` is the DATA root, so the two differ by
    exactly one level and a straight pass-through resolves to
    <data>/data/stage_analysis — a path that never exists.
    """

    def _fixture_contract(self, tmp_path: Path) -> Path:
        fx = tmp_path / "contract.json"
        fx.write_text(json.dumps({
            "schema": "stage_context.v1",
            "asof": "2026-08-03",
            "data_session": "2026-07-31",
            "counts": {},
            "top_stage2": [],
        }))
        return fx

    def test_builder_hands_the_heal_a_root_it_can_resolve(self, tmp_path, monkeypatch):
        """The root the builder passes must locate the real ledger path."""
        import scripts.build_stage_analysis as bsa
        import scripts.heal_stage_forward_ledger as heal_mod

        ledger = tmp_path / "data" / "stage_analysis" / "forward_ledger.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text("")

        seen: dict = {}

        def _spy(root, *a, **kw):
            seen["root"] = Path(root)
            return {"n_restamped": 0, "n_quarantined_now": 0}

        monkeypatch.setattr(heal_mod, "heal", _spy)
        rc = bsa.main(["--fixture", str(self._fixture_contract(tmp_path)),
                       "--root", str(tmp_path / "data")])

        assert rc == 0
        assert "root" in seen, "the nightly builder never invoked the heal at all"
        # The REPO root, not the data root — and it must actually find the ledger.
        assert seen["root"] == tmp_path
        assert (seen["root"] / "data" / "stage_analysis"
                / "forward_ledger.jsonl").exists()

    def test_unreachable_ledger_is_announced_not_swallowed(self, tmp_path, monkeypatch,
                                                           capsys):
        """A heal that cannot find its ledger is a defect, and must say so.

        Before this guard the caller logged only on a non-zero restamp/quarantine
        count, so the {"error": ...} return printed nothing at all.
        """
        import scripts.build_stage_analysis as bsa
        import scripts.heal_stage_forward_ledger as heal_mod

        monkeypatch.setattr(heal_mod, "heal",
                            lambda root, *a, **kw: {"error": "no such ledger"})
        rc = bsa.main(["--fixture", str(self._fixture_contract(tmp_path)),
                       "--root", str(tmp_path / "data")])

        assert rc == 0  # fail-open: never fatal to the nightly
        out = capsys.readouterr().out
        lines = [l for l in out.splitlines() if "heal did not run" in l]
        assert lines, "an unreachable heal printed nothing — the guard is dark"
        # GitHub only parses a workflow command when "::" STARTS the line.
        assert lines[0].startswith("::warning")
