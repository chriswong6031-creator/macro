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

FIXTURE = Path(__file__).parent / "fixtures" / "stage_context_latest.json"


# ---------------------------------------------------------------------------
# Fake classifier — deterministic per-ticker stage dicts, no price math.
# ---------------------------------------------------------------------------
def _fake_stage_map() -> dict[str, dict]:
    """A tidy universe covering every stage + a too-young + an unclassifiable."""
    return {
        # ticker: (stage, weeks, fresh, slope, pct_vs_ma30, mrs, vol_ratio, event, arc, n_weeks)
        "NVDA": dict(stage=2, weeks_in_stage=6, fresh=True, ma30_slope_pct5w=3.4,
                     pct_vs_ma30=8.9, mansfield_rs=12.0, vol_ratio=1.72,
                     event="breakout", arc_pos=0.31, n_weeks=200),
        "AVGO": dict(stage=2, weeks_in_stage=9, fresh=True, ma30_slope_pct5w=2.1,
                     pct_vs_ma30=5.3, mansfield_rs=6.0, vol_ratio=1.31,
                     event="trendline_recapture", arc_pos=0.38, n_weeks=200),
        "COST": dict(stage=2, weeks_in_stage=22, fresh=False, ma30_slope_pct5w=1.0,
                     pct_vs_ma30=4.1, mansfield_rs=2.0, vol_ratio=0.98,
                     event=None, arc_pos=0.46, n_weeks=200),
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
def test_schema_completeness_vs_fixture(env):
    dr, _ = env
    fixture = json.loads(FIXTURE.read_text())
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")

    # Top-level keys match the fixture exactly.
    assert set(contract.keys()) == set(fixture.keys()), (
        set(fixture.keys()) - set(contract.keys()),
        set(contract.keys()) - set(fixture.keys()))

    assert contract["schema"] == "stage_context.v1"
    assert contract["is_context_only"] is True
    assert contract["display_only"] is True

    # counts / market key sets match.
    assert set(contract["counts"].keys()) == set(fixture["counts"].keys())
    assert set(contract["market"].keys()) == set(fixture["market"].keys())

    # A top_stage2 row carries every field the fixture rows do.
    fx_row_keys = set(fixture["top_stage2"][0].keys())
    assert contract["top_stage2"], "expected at least one Stage-2 name"
    assert set(contract["top_stage2"][0].keys()) == fx_row_keys
    fx_earn_keys = set(fixture["top_stage2"][0]["earnings"].keys())
    assert set(contract["top_stage2"][0]["earnings"].keys()) == fx_earn_keys


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
# 5. Cross-day rollover — a new day re-bases the diff to the prior snapshot.
# ---------------------------------------------------------------------------
def test_cross_day_rollover(env):
    dr, _ = env
    # Day 1 (no prior contract): empty change set.
    c1 = sa.build_context_feed(root=dr, asof="2026-07-17")
    assert c1["changes"]["items"] == []
    assert c1["prev_state"]["by_key"] == {}

    # Day 2 same universe -> no stage changes -> empty items, but prev_state now
    # carries day-1's snapshot as the diff base (asof rolled).
    c2 = sa.build_context_feed(root=dr, asof="2026-07-18")
    assert c2["prev_state"]["asof"] == "2026-07-17"
    assert c2["prev_state"]["by_key"] == c1["_current_by_key"]
    assert c2["changes"]["items"] == []  # nothing moved between the two identical days


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
    contract = sa.build_context_feed(root=dr, asof="2026-07-17")
    by_tk = {r["ticker"]: r for r in contract["top_stage2"]}
    assert by_tk["NVDA"]["earnings"]["present"] is True
    assert by_tk["NVDA"]["earnings"]["tone_word"] == "upbeat"
    assert by_tk["NVDA"]["earnings"]["tags"] == ["guidance_raised"]
    assert by_tk["COST"]["earnings"]["tone_word"] == "downbeat"
    assert by_tk["COST"]["earnings"]["tags"] == ["miss_and_cut"]


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
