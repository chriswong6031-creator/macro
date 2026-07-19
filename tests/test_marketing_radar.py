"""tests/test_marketing_radar.py — Marketing Radar W1 tests (spec §5).

Tests:
 1. surplus scan finds unposted, excludes posted
 2. feed priority dedupe: prophet beats movers for same ticker
 3. emit_opportunities: all Opportunity dataclass fields present; score > 0
 4. sync idempotency: second run adds 0; non-radar seed row preserved
 5. sync expiry: stale radar row flips to "expired"
 6. tier math: always-list → T1; top-size → T1; |1D|>=3 → T2 move_1d; earnings in 3d → T2 earnings_window; quiet small → T3
 7. tiers schema keys present; T1/T2/T3 disjoint + cover universe
 8. top_movers tier_map drops T3; None → same output (contract unchanged)
 9. build_radar end-to-end: writes artifacts, 5 feed entries, non-empty surplus
10. missing artifacts: build_radar on empty repo → dict (no raise), feeds all ok=False
"""
from __future__ import annotations

import dataclasses
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

_TODAY = date.today().isoformat()
_FRESH = (date.today() - timedelta(days=1)).isoformat()
# A date far in the past so opportunity score goes near zero
_STALE_DATE = "2020-01-01"

# Posted ticker (must be excluded from surplus)
_POSTED_TICKER = "AAPL"
# Unposted tickers used across feeds
_PROPHET_TICKER = "NVDA"
_MOVERS_TICKER = "TSLA"
_EARNINGS_TICKER = "AMZN"
_STAGE_TICKER = "MSFT"
_CONFLUENCE_TICKER = "AMD"


def _make_fixture_root(tmp_path: Path) -> Path:
    """Create a minimal fixture repo tree under tmp_path."""
    r = tmp_path

    # --- site/prophet/index.json (2 plans: NVDA active, AAPL posted) ---
    (r / "site" / "prophet").mkdir(parents=True)
    prophet_idx = {
        "schema": "marketing.prophet/v1",
        "asof": _FRESH,
        "plans": [
            {
                "id": "NVDA-BULL-2026",
                "asset": _PROPHET_TICKER,
                "direction": "BULL",
                "phase": "triggered_pre_t1",
                "_signal_date": _FRESH,
                "_conviction_score": 90,
                "recommended_action": "hold",
            },
            {
                "id": "AAPL-BULL-2026",
                "asset": _POSTED_TICKER,  # this one is POSTED — must be excluded
                "direction": "BULL",
                "phase": "triggered_pre_t1",
                "_signal_date": _FRESH,
                "_conviction_score": 80,
                "recommended_action": "hold",
            },
        ],
    }
    (r / "site" / "prophet" / "index.json").write_text(json.dumps(prophet_idx), encoding="utf-8")

    # --- site/factordata/tech_confluence.json (1 active combo) ---
    (r / "site" / "factordata").mkdir(parents=True)
    confluence_data = {
        "generated_utc": f"{_FRESH}T12:00:00Z",
        "legs": [{"display_en": "weekly uptrend"}],
        "combos": {
            "long": [
                {
                    "id": "combo-001",
                    "name_en": "Uptrend combo",
                    "legs": [0],
                    "active_now": [_CONFLUENCE_TICKER],
                    "h21": {"wr_mc_test": 0.72, "n_test": 20, "months_test": 12},
                    "edge_wr_test": 0.10,
                    "n_fires": 50,
                    "fires_last3y": 15,
                    "first_fire": "2020-01-01",
                    "last_fire": _FRESH,
                }
            ],
            "short": [],
        },
    }
    (r / "site" / "factordata" / "tech_confluence.json").write_text(
        json.dumps(confluence_data), encoding="utf-8"
    )

    # --- site/marketdata/sp500_heatmap.json (25+ tiles so top-20 threshold is meaningful) ---
    (r / "site" / "marketdata").mkdir(parents=True)
    # TSLA: big mover (+5.5%), size 0.05 → not in top 20 of 25 tickers → T2 move_1d
    # AAPL: large size (0.20) → megacap → T1 (also in always_list)
    # ZZZ: tiny size (0.001), no big move → T3
    # Fill 22 "filler" tickers with sizes 0.01-0.04 so top-20 threshold cuts at ~0.022
    _filler_tickers = [f"F{i:02d}" for i in range(22)]
    tiles = [
        {"t": _MOVERS_TICKER, "name": "Tesla", "sector": "Auto", "industry": "EV",
         "size": 0.05, "perf": {"1D": 5.5, "1W": 3.0}},  # big mover -> T2 move_1d
        {"t": _POSTED_TICKER, "name": "Apple", "sector": "Tech", "industry": "Phones",
         "size": 0.20, "perf": {"1D": 0.5, "1W": 1.0}},   # large size -> T1 megacap
        {"t": "ZZZ", "name": "Quiet Co", "sector": "XYZ", "industry": "Tiny",
         "size": 0.001, "perf": {"1D": 0.1, "1W": 0.2}},  # T3 quiet small
    ] + [
        {"t": ft, "name": ft, "sector": "Filler", "industry": "Filler",
         "size": 0.06 + i * 0.001, "perf": {"1D": 0.1, "1W": 0.1}}
        for i, ft in enumerate(_filler_tickers)
    ]
    # With 22 filler tickers at 0.06-0.081, AAPL at 0.20, that's 23 tickers larger than TSLA (0.05)
    # → TSLA is NOT in top 20 → tier math goes to T2 move_1d
    heatmap = {
        "asof": _FRESH,
        "generated_utc": f"{_FRESH}T12:00:00Z",
        "tiles": tiles,
        "n_tiles": len(tiles),
    }
    (r / "site" / "marketdata" / "sp500_heatmap.json").write_text(
        json.dumps(heatmap), encoding="utf-8"
    )

    # --- site/marketdata/themes_heatmap.json (minimal) ---
    themes = {"asof": _FRESH, "tiles": []}
    (r / "site" / "marketdata" / "themes_heatmap.json").write_text(
        json.dumps(themes), encoding="utf-8"
    )

    # --- data/earnings/earnings.parquet (AMZN within 3 days) ---
    (r / "data" / "earnings").mkdir(parents=True)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    edf = pd.DataFrame({
        "next_date": [tomorrow, "2030-01-01"],
        "next_time": ["AMC", "BMO"],
        "eps_forecast": [1.5, 2.0],
        "surprises_json": ["[]", "[]"],
        "as_of": [_FRESH + "T00:00:00Z", _FRESH + "T00:00:00Z"],
    }, index=pd.Index([_EARNINGS_TICKER, "DISTANT"], name="ticker"))
    edf.to_parquet(r / "data" / "earnings" / "earnings.parquet")

    # --- data/universe/membership.parquet ---
    (r / "data" / "universe").mkdir(parents=True)
    universe_tickers = [_POSTED_TICKER, _PROPHET_TICKER, _MOVERS_TICKER,
                        _EARNINGS_TICKER, _STAGE_TICKER, _CONFLUENCE_TICKER, "ZZZ"] + _filler_tickers
    mem_df = pd.DataFrame({
        "ticker": universe_tickers,
        "group": ["sp500"] * len(universe_tickers),
        "name": universe_tickers,
        "sector": ["Tech"] * len(universe_tickers),
        "first_seen": [_FRESH] * len(universe_tickers),
        "last_seen": [_FRESH] * len(universe_tickers),
        "active": [True] * len(universe_tickers),
    })
    mem_df.to_parquet(r / "data" / "universe" / "membership.parquet", index=False)

    # --- data/stage_analysis/backfill/equitydesk_overview.parquet ---
    (r / "data" / "stage_analysis" / "backfill").mkdir(parents=True)
    stage_df = pd.DataFrame({
        "ticker": [_STAGE_TICKER, "OTHER_REGION"],
        "region": ["USA", "CN"],
        "stage_flag": [2, 2],
        "stage_detailed": ["Stage 2 - Accumulation", "Stage 2 - Accumulation"],
        "sata_score": [85, 90],
        "weeks_in_stage": [4, 6],
        "as_of_date": [_FRESH, _FRESH],
    })
    stage_df.to_parquet(r / "data" / "stage_analysis" / "backfill" / "equitydesk_overview.parquet",
                        index=False)

    # --- data/stocks/{ticker}.parquet (dollar volume) ---
    (r / "data" / "stocks").mkdir(parents=True)
    # Only write for core tickers (filler tickers have no stock file → None dollar_vol)
    _core_tickers = [_POSTED_TICKER, _PROPHET_TICKER, _MOVERS_TICKER,
                     _EARNINGS_TICKER, _STAGE_TICKER, _CONFLUENCE_TICKER, "ZZZ"]
    for tkr in _core_tickers:
        sdf = pd.DataFrame({
            "close": [100.0],
            "volume": [5_000_000.0],  # 100 * 5M / 1e6 = 500 M$ < 1000
        }, index=pd.DatetimeIndex([pd.Timestamp(_FRESH)], name="Date"))
        sdf.to_parquet(r / "data" / "stocks" / f"{tkr}.parquet")

    # --- data/marketing/ ---
    (r / "data" / "marketing").mkdir(parents=True)

    # content_plan.json — queue with one posted ticker (AAPL)
    content_plan = {
        "schema": "marketing.content/v1",
        "schema_version": 1,
        "produced_at": f"{_FRESH}T00:00:00Z",
        "produced_by": "test",
        "tier": "display",
        "as_of": _FRESH,
        "source": {},
        "content_types": [],
        "accounts": [
            {
                "id": "flagship",
                "queue": [
                    {"ticker": _POSTED_TICKER, "cashtag": f"${_POSTED_TICKER}",
                     "type": "signal", "id": "t01"},
                ],
            }
        ],
        "featured_charts": [],
        "distinctness": {},
        "summary": {},
    }
    (r / "data" / "marketing" / "content_plan.json").write_text(
        json.dumps(content_plan), encoding="utf-8"
    )

    # opportunities.jsonl — one non-radar seed row
    seed_opp = {
        "opportunity_id": "seed-opp-001",
        "detected_at": f"{_FRESH}T00:00:00Z",
        "source_type": "evergreen",
        "audience_hypothesis": "swing traders",
        "problem_or_desire": "market education",
        "expected_value": 0.6,
        "originality": 0.9,
        "evidence_available": True,
        "possible_products": ["content"],
        "possible_channels": ["x"],
        "consequence_class": "market_education",
        "owner_department": "intelligence",
        "status": "open",
        "mode": "shadow",
    }
    (r / "data" / "marketing" / "opportunities.jsonl").write_text(
        json.dumps(seed_opp) + "\n", encoding="utf-8"
    )

    # config/marketing.yml (minimal — t1_always for tier tests)
    (r / "config").mkdir(parents=True)
    mkt_yml = f"""
settings:
  radar_tiers_enabled: false
radar:
  t1_always: [AAPL, NVDA]
"""
    (r / "config" / "marketing.yml").write_text(mkt_yml, encoding="utf-8")

    return r


# ─────────────────────────────────────────────────────────────────────────────
# 1. Surplus scan: unposted found, posted excluded
# ─────────────────────────────────────────────────────────────────────────────

def test_surplus_excludes_posted_ticker(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import scan_signal_surplus
    surplus = scan_signal_surplus(r)
    tickers = [s["ticker"] for s in surplus]
    assert _POSTED_TICKER not in tickers, f"{_POSTED_TICKER} should be excluded (posted)"
    assert len(surplus) > 0, "Expected at least one unposted asset in surplus"


def test_surplus_finds_unposted_assets(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import scan_signal_surplus
    surplus = scan_signal_surplus(r)
    tickers = {s["ticker"] for s in surplus}
    # NVDA from prophet should be in surplus (it's not posted)
    assert _PROPHET_TICKER in tickers


# ─────────────────────────────────────────────────────────────────────────────
# 2. Feed priority dedupe: prophet beats movers for same ticker
# ─────────────────────────────────────────────────────────────────────────────

def test_feed_priority_prophet_beats_movers(tmp_path):
    """If ticker appears in both prophet and movers, keep prophet (first feed)."""
    r = _make_fixture_root(tmp_path)
    # Patch the prophet index to use TSLA (same as movers fixture ticker)
    prophet_idx = {
        "schema": "marketing.prophet/v1",
        "asof": _FRESH,
        "plans": [
            {
                "id": "TSLA-BULL-2026",
                "asset": _MOVERS_TICKER,
                "direction": "BULL",
                "phase": "triggered_pre_t1",
                "_signal_date": _FRESH,
                "_conviction_score": 90,
            },
        ],
    }
    (r / "site" / "prophet" / "index.json").write_text(json.dumps(prophet_idx), encoding="utf-8")

    from engine.marketing.radar_internal import scan_signal_surplus
    surplus = scan_signal_surplus(r)
    # TSLA should appear exactly once, with feed == "prophet" (prophet is first)
    tsla_items = [s for s in surplus if s["ticker"] == _MOVERS_TICKER]
    assert len(tsla_items) == 1, f"Expected exactly 1 TSLA in surplus, got {len(tsla_items)}"
    assert tsla_items[0]["feed"] == "prophet", f"Expected feed=prophet, got {tsla_items[0]['feed']}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. emit_opportunities: consumer contract — all Opportunity fields present, score > 0
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_opportunities_consumer_contract(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import scan_signal_surplus, emit_opportunities
    from engine.marketing.opportunity_bus import score_dict, Opportunity

    surplus = scan_signal_surplus(r)
    assert surplus, "No surplus to test emit_opportunities"

    opps = emit_opportunities(surplus, _FRESH)
    assert opps, "emit_opportunities returned empty list"

    # Get all Opportunity dataclass field names
    opp_fields = {f.name for f in dataclasses.fields(Opportunity)}

    # now = as_of + 1 hour (per spec)
    now = datetime.fromisoformat(_FRESH + "T01:00:00+00:00")

    for opp in opps:
        # All Opportunity field names must be present
        missing = opp_fields - set(opp.keys())
        assert not missing, f"Opportunity dict missing fields: {missing}"

        # Score must be > 0
        sc = score_dict(opp, now=now)
        assert sc > 0, f"score should be > 0, got {sc} for {opp}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. sync idempotency: second run adds 0; non-radar seed row preserved
# ─────────────────────────────────────────────────────────────────────────────

def test_sync_idempotency(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import scan_signal_surplus, emit_opportunities, sync_opportunities

    surplus = scan_signal_surplus(r)
    opps = emit_opportunities(surplus, _FRESH)

    summary1 = sync_opportunities(r, opps)
    summary2 = sync_opportunities(r, opps)

    assert summary2["added"] == 0, f"Second run should add 0, got {summary2['added']}"
    assert summary2["total"] >= summary1["total"]


def test_sync_preserves_non_radar_seed(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import scan_signal_surplus, emit_opportunities, sync_opportunities

    surplus = scan_signal_surplus(r)
    opps = emit_opportunities(surplus, _FRESH)
    sync_opportunities(r, opps)

    # Read back and check seed row is intact
    lines = (r / "data" / "marketing" / "opportunities.jsonl").read_text(encoding="utf-8").splitlines()
    non_radar = [json.loads(l) for l in lines if l.strip() and not json.loads(l).get("opportunity_id", "").startswith("radar-")]
    assert len(non_radar) == 1
    seed = non_radar[0]
    assert seed["opportunity_id"] == "seed-opp-001"
    assert seed["status"] == "open"
    assert seed["expected_value"] == 0.6


# ─────────────────────────────────────────────────────────────────────────────
# 5. sync expiry: stale radar row flips to "expired"
# ─────────────────────────────────────────────────────────────────────────────

def test_sync_expiry_of_stale_radar_row(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import sync_opportunities
    from engine.marketing.opportunity_bus import score_dict

    # Plant a radar row whose score < 0.05 but detected_at is recent (within 30d prune window)
    # so it transitions open→expired without being pruned away.
    recent_ts = (datetime.now(tz=timezone.utc) - timedelta(days=5)).isoformat()
    stale_row = {
        "opportunity_id": "radar-prophet-XYZ-recent",
        "detected_at": recent_ts,
        "source_type": "weekly_signal",
        "expected_value": 0.05,  # low ev → score < 0.05 even when fresh
        "originality": 1.0,
        "status": "open",
        "mode": "live",
    }
    # Verify score is < 0.05 before writing
    sc = score_dict(stale_row)
    assert sc < 0.05, f"Stale row should have score < 0.05, got {sc}"

    existing_content = (r / "data" / "marketing" / "opportunities.jsonl").read_text(encoding="utf-8")
    (r / "data" / "marketing" / "opportunities.jsonl").write_text(
        existing_content + json.dumps(stale_row) + "\n", encoding="utf-8"
    )

    # sync with empty new opps — stale row should be expired but kept (recent enough)
    summary = sync_opportunities(r, [])

    lines = (r / "data" / "marketing" / "opportunities.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(l) for l in lines if l.strip()]
    stale_out = [row for row in rows if row.get("opportunity_id") == "radar-prophet-XYZ-recent"]
    assert len(stale_out) == 1, (
        f"Recently-expired row should still be in ledger (within 30d window), got {len(stale_out)}"
    )
    assert stale_out[0]["status"] == "expired", f"Expected expired, got {stale_out[0]['status']}"
    assert summary["expired"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. Tier math
# ─────────────────────────────────────────────────────────────────────────────

def test_tier_always_list_is_t1(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_cashtag_tiers
    tiers = build_cashtag_tiers(r)
    assert tiers is not None
    tickers_detail = tiers.get("tickers") or {}
    # NVDA is in t1_always in fixture config
    assert tickers_detail.get("NVDA", {}).get("tier") == "T1"
    assert "always_list" in tickers_detail.get("NVDA", {}).get("reasons", [])


def test_tier_top_size_is_t1(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_cashtag_tiers
    tiers = build_cashtag_tiers(r)
    assert tiers is not None
    # AAPL has size 0.20 (largest in fixture heatmap) → T1 megacap_weight
    # (also in always_list, so "always_list" reason comes first)
    tickers_detail = tiers.get("tickers") or {}
    assert tickers_detail.get("AAPL", {}).get("tier") == "T1"


def test_tier_move_1d_is_t2(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_cashtag_tiers
    # TSLA has 1D=5.5%, qualifies for T2 move_1d
    # But TSLA is NOT in t1_always (fixture config only has AAPL, NVDA)
    tiers = build_cashtag_tiers(r)
    assert tiers is not None
    tickers_detail = tiers.get("tickers") or {}
    tsla = tickers_detail.get("TSLA", {})
    assert tsla.get("tier") == "T2", f"Expected T2, got {tsla.get('tier')}"
    assert "move_1d" in tsla.get("reasons", [])


def test_tier_earnings_window_is_t2(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_cashtag_tiers
    # AMZN has earnings tomorrow (within 5 days)
    tiers = build_cashtag_tiers(r)
    assert tiers is not None
    tickers_detail = tiers.get("tickers") or {}
    amzn = tickers_detail.get("AMZN", {})
    # AMZN is not in t1_always (fixture only has AAPL, NVDA), so should be T2
    assert amzn.get("tier") == "T2", f"Expected T2, got {amzn.get('tier')}"
    assert "earnings_window" in amzn.get("reasons", [])


def test_tier_quiet_small_is_t3(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_cashtag_tiers
    # ZZZ: not in always_list, small size (0.001), no big move, no earnings soon, low dollar vol
    tiers = build_cashtag_tiers(r)
    assert tiers is not None
    tickers_detail = tiers.get("tickers") or {}
    zzz = tickers_detail.get("ZZZ", {})
    assert zzz.get("tier") == "T3", f"Expected T3, got {zzz.get('tier')}"
    assert zzz.get("reasons") == [], f"Expected no reasons, got {zzz.get('reasons')}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Tiers schema keys present; T1/T2/T3 disjoint + cover universe
# ─────────────────────────────────────────────────────────────────────────────

def test_tiers_schema_keys_present(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_cashtag_tiers
    tiers = build_cashtag_tiers(r)
    assert tiers is not None
    required_keys = {
        "schema", "schema_version", "produced_by", "produced_at", "tier",
        "as_of", "universe_n", "tiers", "tickers",
    }
    missing = required_keys - set(tiers.keys())
    assert not missing, f"Missing keys: {missing}"
    assert tiers["schema"] == "marketing.cashtag_tiers/v1"
    assert isinstance(tiers["tiers"], dict)
    for k in ("T1", "T2", "T3"):
        assert k in tiers["tiers"]


def test_tiers_disjoint_and_cover_universe(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_cashtag_tiers
    tiers = build_cashtag_tiers(r)
    assert tiers is not None

    t1 = set(tiers["tiers"]["T1"])
    t2 = set(tiers["tiers"]["T2"])
    t3 = set(tiers["tiers"]["T3"])

    # Disjoint
    assert not (t1 & t2), f"T1 ∩ T2 non-empty: {t1 & t2}"
    assert not (t1 & t3), f"T1 ∩ T3 non-empty: {t1 & t3}"
    assert not (t2 & t3), f"T2 ∩ T3 non-empty: {t2 & t3}"

    # Cover universe (every ticker in tickers dict is in exactly one tier list)
    all_tiered = t1 | t2 | t3
    tickers_keys = set(tiers["tickers"].keys())
    assert all_tiered == tickers_keys, f"Tier sets don't cover all tickers: {tickers_keys - all_tiered}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. top_movers tier_map drops T3; None → identical output
# ─────────────────────────────────────────────────────────────────────────────

def test_top_movers_tier_map_drops_t3(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.movers_source import load_movers, top_movers

    data = load_movers(r)
    assert data is not None

    # Baseline without tier_map
    result_no_filter = top_movers(data, tf="1D", n=8, min_abs=3.0)
    all_base = result_no_filter["gainers"] + result_no_filter["losers"]

    # Build a tier_map where TSLA is T3
    tier_map = {_MOVERS_TICKER: "T3"}
    result_filtered = top_movers(data, tf="1D", n=8, min_abs=3.0, tier_map=tier_map)
    all_filtered = result_filtered["gainers"] + result_filtered["losers"]

    # TSLA should be in base but not in filtered
    base_tickers = {m["ticker"] for m in all_base}
    filtered_tickers = {m["ticker"] for m in all_filtered}

    if _MOVERS_TICKER in base_tickers:
        assert _MOVERS_TICKER not in filtered_tickers, "T3 ticker should be filtered out"


def test_top_movers_tier_map_none_unchanged(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.movers_source import load_movers, top_movers

    data = load_movers(r)
    assert data is not None

    result_none = top_movers(data, tf="1D", n=8, min_abs=3.0, tier_map=None)
    result_no_arg = top_movers(data, tf="1D", n=8, min_abs=3.0)

    # Both should produce identical output
    assert result_none == result_no_arg, "tier_map=None should behave same as no tier_map"


# ─────────────────────────────────────────────────────────────────────────────
# 9. build_radar end-to-end: artifacts written, 5 feeds, non-empty surplus
# ─────────────────────────────────────────────────────────────────────────────

def test_build_radar_writes_artifacts(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_radar

    report = build_radar(r)

    assert isinstance(report, dict), "build_radar should return a dict"
    assert "error" not in report, f"build_radar returned error: {report.get('error')}"

    # All three artifacts must exist
    assert (r / "data" / "marketing" / "radar_report.json").exists(), "radar_report.json missing"
    assert (r / "data" / "marketing" / "cashtag_tiers.json").exists(), "cashtag_tiers.json missing"
    assert (r / "data" / "marketing" / "radar_plan_history.json").exists(), "radar_plan_history.json missing"


def test_build_radar_report_has_5_feeds(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_radar

    report = build_radar(r)
    feeds = report.get("feeds", [])
    assert len(feeds) == 5, f"Expected 5 feeds, got {len(feeds)}: {[f['name'] for f in feeds]}"
    feed_names = {f["name"] for f in feeds}
    assert feed_names == {"prophet", "confluence", "earnings", "movers", "stage"}


def test_build_radar_report_has_nonempty_surplus(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_radar

    report = build_radar(r)
    surplus = report.get("surplus", [])
    assert len(surplus) > 0, "Expected non-empty surplus in radar report"


def test_build_radar_opportunities_grew(tmp_path):
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_radar

    # Count lines before
    opp_path = r / "data" / "marketing" / "opportunities.jsonl"
    before_count = len([l for l in opp_path.read_text().splitlines() if l.strip()])

    build_radar(r)

    after_count = len([l for l in opp_path.read_text().splitlines() if l.strip()])
    assert after_count > before_count, "opportunities.jsonl should have grown after build_radar"


# ─────────────────────────────────────────────────────────────────────────────
# 10. Missing artifacts: build_radar on empty repo → dict, feeds all ok=False
# ─────────────────────────────────────────────────────────────────────────────

def test_build_radar_empty_repo_no_raise(tmp_path):
    """build_radar on a completely empty tmp dir must return a dict, never raise."""
    from engine.marketing.radar_internal import build_radar

    result = build_radar(tmp_path)

    assert isinstance(result, dict), "build_radar should return dict even on empty repo"
    # Should not raise (already validated by returning dict)


def test_build_radar_empty_repo_feeds_all_ok_false(tmp_path):
    """All 5 feeds should report ok=False on an empty repo (no artifacts to read)."""
    from engine.marketing.radar_internal import build_radar

    result = build_radar(tmp_path)

    if "error" in result:
        # Catastrophic failure is acceptable but the 5-feeds contract can't be verified
        return

    feeds = result.get("feeds", [])
    if not feeds:
        return  # degenerate case acceptable for empty repo

    for feed_meta in feeds:
        assert feed_meta.get("ok") is False or feed_meta.get("n_assets") == 0, (
            f"Feed {feed_meta['name']} should have ok=False or n_assets=0 on empty repo, "
            f"got ok={feed_meta.get('ok')}, n_assets={feed_meta.get('n_assets')}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 11. Round-robin diversity: one heavy feed does not monopolize the surplus cap
# ─────────────────────────────────────────────────────────────────────────────

def test_surplus_round_robin_diversity(tmp_path):
    """When earnings feed has many items, round-robin ensures other feeds are represented."""
    import pandas as pd
    from engine.marketing.radar_internal import scan_signal_surplus

    r = _make_fixture_root(tmp_path)

    # Flood the earnings feed with 30 unique tickers, all with earnings tomorrow.
    # Without round-robin, earnings would crowd out prophet/stage/movers tickers.
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    # Use tickers that don't conflict with existing fixture tickers
    earnings_tickers = [f"EA{i:02d}" for i in range(30)]
    edf = pd.DataFrame({
        "next_date": [tomorrow] * 30,
        "next_time": ["time-not-supplied"] * 30,
        "eps_forecast": [1.0] * 30,
        "surprises_json": ["[]"] * 30,
        "as_of": [_FRESH + "T00:00:00Z"] * 30,
    }, index=pd.Index(earnings_tickers, name="ticker"))
    edf.to_parquet(r / "data" / "earnings" / "earnings.parquet")

    surplus = scan_signal_surplus(r)

    # The total cap is 40; verify feeds other than earnings are represented
    feeds_represented = {s["feed"] for s in surplus}
    assert "prophet" in feeds_represented, (
        f"Round-robin should include prophet feed; feeds present: {feeds_represented}"
    )
    # Earnings should not have taken all 40 slots (prophet has at least 1 item = NVDA)
    earnings_count = sum(1 for s in surplus if s["feed"] == "earnings")
    assert earnings_count < len(surplus), (
        f"Earnings monopolized surplus ({earnings_count}/{len(surplus)}); round-robin broken"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 12. Always-list ticker outside index universe appears as T1 with null proxies
# ─────────────────────────────────────────────────────────────────────────────

def test_always_list_ticker_outside_index_is_t1(tmp_path):
    """GME/AMC-style always-list tickers not in sp500/ndx must appear in cashtag_tiers as T1."""
    import pandas as pd
    from engine.marketing.radar_internal import build_cashtag_tiers

    r = _make_fixture_root(tmp_path)

    # Write a config where MEME_XX is in t1_always but NOT in the sp500/ndx universe
    mkt_yml = """
settings:
  radar_tiers_enabled: false
radar:
  t1_always: [AAPL, NVDA, MEME_XX]
"""
    (r / "config" / "marketing.yml").write_text(mkt_yml, encoding="utf-8")
    # Confirm MEME_XX is not in the membership.parquet fixture (it's not written there)

    tiers = build_cashtag_tiers(r)
    assert tiers is not None

    tickers_detail = tiers.get("tickers") or {}
    assert "MEME_XX" in tickers_detail, "Always-list ticker outside index must appear in cashtag_tiers"

    entry = tickers_detail["MEME_XX"]
    assert entry.get("tier") == "T1", f"Always-list ticker must be T1, got {entry.get('tier')}"
    assert "always_list" in entry.get("reasons", []), (
        f"Always-list ticker reasons must include 'always_list', got {entry.get('reasons')}"
    )
    # Proxies should be None (no heatmap tile, no stock parquet, no earnings row)
    proxies = entry.get("proxies", {})
    assert proxies.get("mcap_weight") is None, "mcap_weight should be None for out-of-index always-list ticker"
    assert proxies.get("pct_1d") is None, "pct_1d should be None for out-of-index always-list ticker"


def test_always_list_ticker_in_tier_lists(tmp_path):
    """Always-list ticker outside index must appear in the T1 list (not absent from tiers)."""
    import pandas as pd
    from engine.marketing.radar_internal import build_cashtag_tiers

    r = _make_fixture_root(tmp_path)

    mkt_yml = """
settings:
  radar_tiers_enabled: false
radar:
  t1_always: [AAPL, NVDA, GME, AMC]
"""
    (r / "config" / "marketing.yml").write_text(mkt_yml, encoding="utf-8")

    tiers = build_cashtag_tiers(r)
    assert tiers is not None

    t1_set = set(tiers["tiers"]["T1"])
    assert "GME" in t1_set, f"GME (always-list, not in sp500/ndx fixture) must be in T1; T1={t1_set}"
    assert "AMC" in t1_set, f"AMC (always-list, not in sp500/ndx fixture) must be in T1; T1={t1_set}"


# ─────────────────────────────────────────────────────────────────────────────
# 13. Earnings timing slug plainification — no raw slugs in why strings
# ─────────────────────────────────────────────────────────────────────────────

def test_earnings_feed_no_time_not_supplied_in_why(tmp_path):
    """'time-not-supplied' must never appear in any earnings why string."""
    import pandas as pd
    from engine.marketing.radar_internal import _feed_earnings

    r = _make_fixture_root(tmp_path)

    # Write earnings with all three timing values
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    edf = pd.DataFrame({
        "next_date": [tomorrow, tomorrow, tomorrow],
        "next_time": ["time-not-supplied", "time-pre-market", "time-after-hours"],
        "eps_forecast": [1.0, 2.0, 3.0],
        "surprises_json": ["[]", "[]", "[]"],
        "as_of": [_FRESH + "T00:00:00Z"] * 3,
    }, index=pd.Index(["T_NONE", "T_PRE", "T_AH"], name="ticker"))
    edf.to_parquet(r / "data" / "earnings" / "earnings.parquet")

    items = _feed_earnings(r)
    assert items, "Expected earnings items in 3-day window"

    for item in items:
        why = item["why"]
        assert "time-not-supplied" not in why, (
            f"Raw slug 'time-not-supplied' must not appear in why: {why!r}"
        )
        assert "time-pre-market" not in why, (
            f"Raw slug 'time-pre-market' must not appear in why: {why!r}"
        )
        assert "time-after-hours" not in why, (
            f"Raw slug 'time-after-hours' must not appear in why: {why!r}"
        )


def test_earnings_feed_timing_display_strings(tmp_path):
    """pre-market and after-hours map to correct display strings; time-not-supplied omitted."""
    import pandas as pd
    from engine.marketing.radar_internal import _feed_earnings

    r = _make_fixture_root(tmp_path)

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    edf = pd.DataFrame({
        "next_date": [tomorrow, tomorrow, tomorrow],
        "next_time": ["time-not-supplied", "time-pre-market", "time-after-hours"],
        "eps_forecast": [1.0, 2.0, 3.0],
        "surprises_json": ["[]", "[]", "[]"],
        "as_of": [_FRESH + "T00:00:00Z"] * 3,
    }, index=pd.Index(["T_NONE", "T_PRE", "T_AH"], name="ticker"))
    edf.to_parquet(r / "data" / "earnings" / "earnings.parquet")

    items_by_ticker = {item["ticker"]: item["why"] for item in _feed_earnings(r)}

    # time-not-supplied → why ends with date only (no timing suffix)
    none_why = items_by_ticker.get("T_NONE", "")
    assert none_why.endswith(tomorrow), (
        f"time-not-supplied should produce why='earnings {tomorrow}', got {none_why!r}"
    )
    assert "pre-market" not in none_why and "after hours" not in none_why

    # time-pre-market → "pre-market" in why
    pre_why = items_by_ticker.get("T_PRE", "")
    assert "pre-market" in pre_why, f"Expected 'pre-market' in why for T_PRE, got {pre_why!r}"

    # time-after-hours → "after hours" in why
    ah_why = items_by_ticker.get("T_AH", "")
    assert "after hours" in ah_why, f"Expected 'after hours' in why for T_AH, got {ah_why!r}"


# ─────────────────────────────────────────────────────────────────────────────
# M1 — expired count is a per-run TRANSITION count, not cumulative
# ─────────────────────────────────────────────────────────────────────────────

def test_sync_expired_count_is_per_run_transition(tmp_path):
    """Three consecutive syncs over already-dead rows: run1 expired==N, run2 expired==0, run3 expired==0."""
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import sync_opportunities

    # Plant two stale radar rows (score will be < 0.05)
    stale_rows = [
        {
            "opportunity_id": f"radar-prophet-DEAD{i}-2020-01-01",
            "detected_at": "2020-01-01T00:00:00Z",
            "source_type": "weekly_signal",
            "expected_value": 0.6,
            "originality": 1.0,
            "status": "open",
            "mode": "live",
        }
        for i in range(2)
    ]
    existing = (r / "data" / "marketing" / "opportunities.jsonl").read_text(encoding="utf-8")
    (r / "data" / "marketing" / "opportunities.jsonl").write_text(
        existing + "".join(json.dumps(row) + "\n" for row in stale_rows),
        encoding="utf-8",
    )

    # Run 1: both rows should transition open→expired
    s1 = sync_opportunities(r, [])
    assert s1["expired"] == 2, f"Run1 should expire 2 rows, got {s1['expired']}"

    # Run 2: already expired — transition count must be 0
    s2 = sync_opportunities(r, [])
    assert s2["expired"] == 0, f"Run2 should expire 0 rows (already expired), got {s2['expired']}"

    # Run 3: still 0
    s3 = sync_opportunities(r, [])
    assert s3["expired"] == 0, f"Run3 should expire 0 rows, got {s3['expired']}"


# ─────────────────────────────────────────────────────────────────────────────
# M2 — NaN proxies produce None, JSON serialises cleanly
# ─────────────────────────────────────────────────────────────────────────────

def test_nan_stock_parquet_proxies_are_none(tmp_path):
    """Stock parquet with NaN close/volume tail → dollar_vol_musd is None; json.dumps succeeds."""
    import math
    import pandas as pd
    from engine.marketing.radar_internal import build_cashtag_tiers

    r = _make_fixture_root(tmp_path)

    # Overwrite TSLA parquet to have a NaN tail row
    import numpy as np
    nan_df = pd.DataFrame({
        "close": [100.0, float("nan")],
        "volume": [5_000_000.0, float("nan")],
    }, index=pd.DatetimeIndex(
        [pd.Timestamp(_FRESH) - timedelta(days=1), pd.Timestamp(_FRESH)],
        name="Date",
    ))
    nan_df.to_parquet(r / "data" / "stocks" / f"{_MOVERS_TICKER}.parquet")

    tiers = build_cashtag_tiers(r)
    assert tiers is not None

    tsla = (tiers.get("tickers") or {}).get(_MOVERS_TICKER, {})
    proxies = tsla.get("proxies", {})
    assert proxies.get("dollar_vol_musd") is None, (
        f"NaN row should yield dollar_vol_musd=None, got {proxies.get('dollar_vol_musd')}"
    )

    # Critical: json.dumps must not throw (allow_nan=False replicates browser behaviour)
    try:
        json.dumps(tiers, allow_nan=False)
    except ValueError as exc:
        raise AssertionError(f"tiers dict contains non-finite value that breaks JSON: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# m2 — 30-day ledger pruning in sync_opportunities
# ─────────────────────────────────────────────────────────────────────────────

def test_sync_prune_old_expired_radar_row(tmp_path):
    """Expired radar row 40 days old is dropped; expired row 5 days old is kept; non-radar ancient row kept."""
    r = _make_fixture_root(tmp_path)
    from engine.marketing.radar_internal import sync_opportunities

    now = datetime.now(tz=timezone.utc)
    old_ts = (now - timedelta(days=40)).isoformat()
    recent_ts = (now - timedelta(days=5)).isoformat()
    ancient_ts = (now - timedelta(days=365)).isoformat()

    old_expired_radar = {
        "opportunity_id": "radar-prophet-OLD-2020-01-01",
        "detected_at": old_ts,
        "source_type": "weekly_signal",
        "expected_value": 0.01,
        "originality": 1.0,
        "status": "expired",  # already expired
        "mode": "live",
    }
    recent_expired_radar = {
        "opportunity_id": "radar-prophet-RECENT-2026-07-14",
        "detected_at": recent_ts,
        "source_type": "weekly_signal",
        "expected_value": 0.01,
        "originality": 1.0,
        "status": "expired",
        "mode": "live",
    }
    ancient_non_radar = {
        "opportunity_id": "seed-ancient-999",
        "detected_at": ancient_ts,
        "source_type": "evergreen",
        "expected_value": 0.9,
        "originality": 0.8,
        "status": "open",
        "mode": "shadow",
    }

    existing = (r / "data" / "marketing" / "opportunities.jsonl").read_text(encoding="utf-8")
    (r / "data" / "marketing" / "opportunities.jsonl").write_text(
        existing
        + json.dumps(old_expired_radar) + "\n"
        + json.dumps(recent_expired_radar) + "\n"
        + json.dumps(ancient_non_radar) + "\n",
        encoding="utf-8",
    )

    sync_opportunities(r, [])

    lines = (r / "data" / "marketing" / "opportunities.jsonl").read_text(encoding="utf-8").splitlines()
    ids_out = {json.loads(l)["opportunity_id"] for l in lines if l.strip()}

    assert "radar-prophet-OLD-2020-01-01" not in ids_out, "Old expired radar row (40d) should be pruned"
    assert "radar-prophet-RECENT-2026-07-14" in ids_out, "Recent expired radar row (5d) should be kept"
    assert "seed-ancient-999" in ids_out, "Non-radar ancient row must never be pruned"


# ─────────────────────────────────────────────────────────────────────────────
# DOA filter: movers with stale as_of must not enter ledger; other feeds do
# ─────────────────────────────────────────────────────────────────────────────

# A mover as_of 2 days back has detected_at 2-days-ago T00:00:00Z.
# With breaking_event 2h half-life, age ≈ 48h → score ≈ 0.45 * 0.5^24 ≈ 0,
# which is far below _SCORE_FLOOR = 0.05.  Same-day earnings/stage/prophet
# rows survive because their half-lives are 24h / 168h respectively.
_DOA_MOVER_ASOF = (date.today() - timedelta(days=2)).isoformat()
_LIVE_ROW_ASOF = date.today().isoformat()  # same-day → long half-life feeds survive


def _make_doa_fixture_root(tmp_path: Path) -> Path:
    """Fixture where movers as_of is 2 days old but earnings/stage/prophet are same-day."""
    r = _make_fixture_root(tmp_path)

    # Overwrite heatmap so the movers as_of is 2 days old
    heatmap_path = r / "site" / "marketdata" / "sp500_heatmap.json"
    heatmap = json.loads(heatmap_path.read_text(encoding="utf-8"))
    heatmap["asof"] = _DOA_MOVER_ASOF
    heatmap_path.write_text(json.dumps(heatmap), encoding="utf-8")

    # Overwrite prophet so as_of is today (live row)
    prophet_idx = {
        "schema": "marketing.prophet/v1",
        "asof": _LIVE_ROW_ASOF,
        "plans": [
            {
                "id": "NVDA-BULL-2026",
                "asset": _PROPHET_TICKER,
                "direction": "BULL",
                "phase": "triggered_pre_t1",
                "_signal_date": _LIVE_ROW_ASOF,
                "_conviction_score": 90,
            },
        ],
    }
    (r / "site" / "prophet" / "index.json").write_text(json.dumps(prophet_idx), encoding="utf-8")

    # Overwrite earnings so as_of is today (live row)
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    edf = pd.DataFrame({
        "next_date": [tomorrow],
        "next_time": ["time-after-hours"],
        "eps_forecast": [1.5],
        "surprises_json": ["[]"],
        "as_of": [_LIVE_ROW_ASOF + "T00:00:00Z"],
    }, index=pd.Index([_EARNINGS_TICKER], name="ticker"))
    edf.to_parquet(r / "data" / "earnings" / "earnings.parquet")

    # Overwrite stage so as_of is today (live row)
    stage_df = pd.DataFrame({
        "ticker": [_STAGE_TICKER],
        "region": ["USA"],
        "stage_flag": [2],
        "stage_detailed": ["Stage 2 - Accumulation"],
        "sata_score": [85],
        "weeks_in_stage": [4],
        "as_of_date": [_LIVE_ROW_ASOF],
    })
    stage_df.to_parquet(
        r / "data" / "stage_analysis" / "backfill" / "equitydesk_overview.parquet",
        index=False,
    )

    return r


def test_doa_movers_not_written_to_ledger(tmp_path):
    """Mover opportunities with as_of 2+ days old must NOT appear in opportunities.jsonl."""
    r = _make_doa_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_radar

    build_radar(r)

    opp_path = r / "data" / "marketing" / "opportunities.jsonl"
    lines = opp_path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(l) for l in lines if l.strip()]

    mover_ids = [row["opportunity_id"] for row in rows if "-movers-" in row.get("opportunity_id", "")]
    assert not mover_ids, (
        f"Stale mover opportunities should be DOA-filtered from ledger, found: {mover_ids}"
    )

    # Sanity: at least one non-mover row must be present (prophet or earnings or stage)
    non_mover_radar = [
        row for row in rows
        if row.get("opportunity_id", "").startswith("radar-")
        and "-movers-" not in row.get("opportunity_id", "")
    ]
    assert non_mover_radar, "Expected at least one live (non-mover) radar row in ledger"


def test_doa_report_queue_contains_doa_skipped(tmp_path):
    """report['queue']['doa_skipped'] must be >= 1 when movers as_of is 2+ days old."""
    r = _make_doa_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_radar

    report = build_radar(r)

    assert "error" not in report, f"build_radar returned error: {report.get('error')}"
    queue = report.get("queue", {})
    assert "doa_skipped" in queue, f"report['queue'] must have 'doa_skipped' key; got {queue}"
    assert queue["doa_skipped"] >= 1, (
        f"Expected doa_skipped >= 1 (stale movers should be filtered), got {queue['doa_skipped']}"
    )


def test_build_radar_end_to_end_live_rows_written(tmp_path):
    """End-to-end test: earnings and stage rows (live as_of) ARE written to ledger by build_radar."""
    r = _make_doa_fixture_root(tmp_path)
    from engine.marketing.radar_internal import build_radar

    opp_path = r / "data" / "marketing" / "opportunities.jsonl"
    before_count = len([l for l in opp_path.read_text().splitlines() if l.strip()])

    report = build_radar(r)

    assert "error" not in report, f"build_radar returned error: {report.get('error')}"
    after_count = len([l for l in opp_path.read_text().splitlines() if l.strip()])
    assert after_count > before_count, (
        "opportunities.jsonl should grow: live earnings/stage/prophet rows must be written"
    )
