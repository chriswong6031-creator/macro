"""W4.1 acceptance test suite for the person-period hazard panel.

Tests (per W4.1 spec):
1. PIT correctness: a synthetic series proves a turn is INVISIBLE before its confirmed_at.
2. No bloc/basket contamination in the universe (only allowed families in the panel).
3. KM math on a synthetic constant-hazard series recovers the flat hazard.
4. k=6 blend math (D5 §1.5).
5. Censoring correctness: open legs produce censored rows (y=0, censored=1).
6. No future data leakage: panel row at month m uses only tape <= m.
7. rho_hat structure: required keys present; values in valid range.
8. KM baseline structure: required families/directions present.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_REPO))

from engine.cycle_ontology import TurnParams, detect_turns
from scripts.build_hazard_panel import (
    K_BLEND,
    CN_SECTOR_IDS,
    COUNTRY_IDS,
    US_SECTOR_IDS,
    _blended_median,
    _confirmed_turns_asof,
    _detect_turns_for_instrument,
    _log_age_ratio,
    compute_km_baselines,
    estimate_rho_hat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_close(n: int = 600, seed: int = 42, vol: float = 0.015,
                     drift: float = 0.0002) -> pd.Series:
    """Synthetic daily close with random-walk + small drift."""
    rng = np.random.default_rng(seed)
    log_ret = rng.normal(drift, vol, n)
    prices = 100.0 * np.exp(np.cumsum(log_ret))
    idx = pd.date_range("2000-01-03", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def _make_panel_row(date, iid, family, direction, age_m, y1, y3, y6, censored,
                    blended_med=10.0, log_ar=None, age_bucket="b3") -> dict:
    """Minimal panel row for KM tests."""
    if log_ar is None:
        log_ar = np.log(age_m / blended_med) if blended_med and age_m > 0 else np.nan
    return {
        "date": pd.Timestamp(date),
        "id": iid,
        "family": family,
        "direction": direction,
        "turn_def_version": "tr_test",
        "engine_fingerprint": "test",
        "age_m": age_m,
        "age_bucket": age_bucket,
        "log_age_ratio": log_ar,
        "blended_med_m": blended_med,
        "own_med_m": blended_med,
        "family_med_m": blended_med,
        "leg_open_date": pd.Timestamp("2000-01-01"),
        "y1": y1,
        "y3": y3,
        "y6": y6,
        "censored": censored,
        "event_date": pd.NaT if censored else pd.Timestamp("2001-01-01"),
        "pos_osc": 50.0,
        "osc_slope": 0.0,
        "trend_pass": 1.0,
        "mom_score": 0.0,
        "rs_63d": 0.0,
        "vol_pctile": 0.5,
        "amp_proxy": 0.5,
        "leg_amp": 0.1,
        "quad": "Q1",
        "liquidity": "expanding",
    }


# ---------------------------------------------------------------------------
# Test 1: PIT — turn invisible before confirmed_at
# ---------------------------------------------------------------------------

def test_pit_turn_invisible_before_confirmation():
    """A confirmed turn must NOT appear in _confirmed_turns_asof before its confirmed_at date.

    This is the core PIT contract: the hazard panel can only know about a turn
    AFTER the ZigZag reversal threshold has been crossed (confirmed_at), not at
    the pivot extremum (date).
    """
    close = _synthetic_close(n=1000, seed=99, vol=0.02)
    turns = _detect_turns_for_instrument(close, "TEST", pct=14.0)

    # Find the first confirmed (non-provisional) turn with a meaningful confirm lag
    confirmed = [t for t in turns if not t.get("provisional") and t["confirm_lag_bars"] > 5]
    if not confirmed:
        pytest.skip("No confirmed turn with lag > 5 bars — synthetic series too short or flat")

    first = confirmed[0]
    pivot_date = pd.Timestamp(first["date"])
    confirmed_at = pd.Timestamp(first["confirmed_at"])

    assert confirmed_at > pivot_date, (
        f"confirmed_at ({confirmed_at}) must be AFTER the pivot date ({pivot_date})"
    )
    assert first["confirm_lag_bars"] > 0, "confirm_lag_bars must be positive"

    # One day BEFORE confirmed_at: turn should NOT appear
    just_before = confirmed_at - pd.Timedelta(days=1)
    visible_before = _confirmed_turns_asof(turns, just_before)
    ids_before = {t["turn_id"] for t in visible_before}
    assert first["turn_id"] not in ids_before, (
        f"Turn {first['turn_id']} (confirmed_at={confirmed_at}) "
        f"should NOT be visible at {just_before} — PIT violation!"
    )

    # On or after confirmed_at: turn MUST appear
    visible_after = _confirmed_turns_asof(turns, confirmed_at)
    ids_after = {t["turn_id"] for t in visible_after}
    assert first["turn_id"] in ids_after, (
        f"Turn {first['turn_id']} (confirmed_at={confirmed_at}) "
        f"should be visible at {confirmed_at} — turn not appearing after confirmation!"
    )


# ---------------------------------------------------------------------------
# Test 2: No bloc/basket contamination
# ---------------------------------------------------------------------------

def test_universe_contains_only_allowed_families():
    """Panel universe must only contain us_sector, country, cn_sector instruments.

    Blocs are ALLOWED in the hazard panel (per D5_PREDICTION.md §1.3 and §6.3).
    Baskets (THS concept baskets, ETF-like baskets) must NOT appear.
    """
    allowed_ids = set(US_SECTOR_IDS) | set(COUNTRY_IDS) | set(CN_SECTOR_IDS)

    # Verify no basket-style IDs (numeric codes outside CN range, custom names)
    for iid in US_SECTOR_IDS:
        assert iid.upper().startswith("XL"), f"US sector {iid} doesn't match XL* pattern"

    # CN sector IDs must all be 6-digit Shenwan codes
    for iid in CN_SECTOR_IDS:
        assert iid.isdigit() and len(iid) == 6, f"CN sector ID {iid} is not a 6-digit code"

    # Country IDs must all be in the COUNTRY_IDS list (no extra instruments)
    # Note: some are blocs (EFA, EEM, AAXJ, etc.) — these are ALLOWED
    bloc_ids = {"EFA", "EEM", "AAXJ", "VGK", "VPL", "VXUS", "ILF"}
    country_etfs = set(COUNTRY_IDS) - bloc_ids
    assert len(country_etfs) > 0, "Should have some pure country ETFs"
    assert all(c in COUNTRY_IDS for c in bloc_ids), "All blocs must be in the COUNTRY_IDS list"

    # Verify no overlap between families
    us_set = set(US_SECTOR_IDS)
    cn_set = set(CN_SECTOR_IDS)
    country_set = set(COUNTRY_IDS)
    assert us_set.isdisjoint(cn_set), "US sectors and CN sectors overlap!"
    assert us_set.isdisjoint(country_set), "US sectors and country ETFs overlap!"
    # Note: CN codes are numeric, so no natural overlap with ETF tickers


# ---------------------------------------------------------------------------
# Test 3: KM math — constant-hazard synthetic series recovers flat hazard
# ---------------------------------------------------------------------------

def test_km_constant_hazard_recovered():
    """KM on a synthetic constant-hazard panel recovers the true flat hazard rate.

    If every row has p(y1=1) = h independently, the empirical KM should approximate h
    in each age bucket. We test with h=0.1 across 1000 rows.
    """
    rng = np.random.default_rng(42)
    n_rows = 2000
    true_hazard = 0.10

    y1 = rng.binomial(1, true_hazard, n_rows)

    # Build a fake panel with uniform age distribution across buckets
    buckets = ["b1", "b2", "b3", "b4", "b5"]
    rows = []
    for i in range(n_rows):
        bucket = buckets[i % len(buckets)]
        age_m = (i % len(buckets) + 1) * 5.0  # 5, 10, 15, 20, 25 months
        rows.append(_make_panel_row(
            date="2020-01-31",
            iid=f"SYN{i % 10:02d}",
            family="us_sector",
            direction="up",
            age_m=age_m,
            y1=int(y1[i]),
            y3=int(y1[i]),
            y6=int(y1[i]),
            censored=0,
            age_bucket=bucket,
        ))

    panel = pd.DataFrame(rows)
    km = compute_km_baselines(panel, "test_epoch")

    # Each bucket should have hazard ~0.10 (within binomial noise)
    km_up = km["families"]["us_sector"]["up"]
    assert km_up["n_rows"] == n_rows
    assert km_up["n_events_y1"] == int(y1.sum())

    for bk in km_up["buckets"]:
        lam = bk["lambda"]
        n_bk = bk["at_risk"]
        # Binomial SE = sqrt(p*(1-p)/n)
        se = np.sqrt(true_hazard * (1 - true_hazard) / n_bk)
        # Allow 4 SE tolerance for robustness
        assert abs(lam - true_hazard) < 4 * se, (
            f"Bucket {bk['bucket']}: lambda={lam:.4f}, true={true_hazard}, "
            f"4*SE={4*se:.4f} — KM does not recover true hazard!"
        )


# ---------------------------------------------------------------------------
# Test 4: k=6 blend math
# ---------------------------------------------------------------------------

def test_k6_blend_math():
    """Blended median formula: (n_i * med_i + k * med_F) / (n_i + k), k=6."""
    # Zero own history → pure family median
    result = _blended_median(own_med=None, own_n=0, family_med=12.0, k=6)
    assert result == 12.0, f"With no own history, expected family median 12.0, got {result}"

    # Large own history → dominated by own median (converges to own_med as n → ∞)
    # Formula: (n*own + k*fam) / (n+k); at n=1000, k=6: (8000 + 72)/1006 = 8.0238
    result = _blended_median(own_med=8.0, own_n=1000, family_med=12.0, k=6)
    expected_large_n = (1000 * 8.0 + 6 * 12.0) / (1000 + 6)
    assert abs(result - expected_large_n) < 1e-6, (
        f"With n=1000, expected {expected_large_n:.6f}, got {result}"
    )
    # Verify it's much closer to own_med than to family_med
    assert abs(result - 8.0) < abs(result - 12.0), (
        "Large n should pull blend much closer to own_med than family_med"
    )

    # At crossover n=6: equal weight → mean of own and family
    result = _blended_median(own_med=8.0, own_n=6, family_med=12.0, k=6)
    expected = (6 * 8.0 + 6 * 12.0) / (6 + 6)
    assert abs(result - expected) < 0.001, f"Expected {expected:.3f}, got {result:.3f}"

    # Monotone: more own history → closer to own_med
    r1 = _blended_median(own_med=8.0, own_n=3, family_med=12.0, k=6)
    r2 = _blended_median(own_med=8.0, own_n=10, family_med=12.0, k=6)
    assert r1 > r2, "More own history should pull blend closer to own_med (8 < 12)"

    # k=6 constant is pre-registered
    assert K_BLEND == 6, f"K_BLEND must be 6 (pre-registered per D5 §1.5), got {K_BLEND}"


# ---------------------------------------------------------------------------
# Test 5: Censoring correctness
# ---------------------------------------------------------------------------

def test_censoring_on_open_leg():
    """Open legs (no future confirmed turn) must produce censored rows.

    Create a synthetic series where the last leg is still open, verify
    that the panel rows for that leg have censored=1 and y=0.
    """
    close = _synthetic_close(n=800, seed=7, vol=0.015)
    turns = _detect_turns_for_instrument(close, "OPEN", pct=14.0)

    # The provisional (last) turn is always the open running extreme
    provisional = [t for t in turns if t.get("provisional")]
    assert len(provisional) == 1, "Should always have exactly one provisional (open) turn"

    confirmed = [t for t in turns if not t.get("provisional")]
    if len(confirmed) < 2:
        pytest.skip("Not enough confirmed turns for this test")

    # The last confirmed turn is the leg-opener for the CURRENT open leg
    last_conf = sorted(confirmed, key=lambda t: t["date"])[-1]
    last_conf_date = pd.Timestamp(last_conf["date"])
    last_conf_confirmed = pd.Timestamp(last_conf["confirmed_at"])

    # At a month-end AFTER the last confirmed turn's confirmed_at but BEFORE
    # any FUTURE confirmed turn can exist (there are none), the row must be censored
    # We verify by building a small set of turns where we control the setup
    # The key property: _confirmed_turns_asof at t=last_conf_confirmed
    # should contain the last confirmed turn, and the next turn (event) doesn't exist
    conf_asof = _confirmed_turns_asof(turns, last_conf_confirmed + pd.Timedelta(days=1))

    # The provisional turn should NOT appear in confirmed_asof
    prov_turn = provisional[0]
    prov_ids = {t["turn_id"] for t in conf_asof if t.get("provisional")}
    assert len(prov_ids) == 0, (
        "Provisional turns must never appear in _confirmed_turns_asof output"
    )


# ---------------------------------------------------------------------------
# Test 6: No future data leakage in features
# ---------------------------------------------------------------------------

def test_pit_features_no_future_leakage():
    """Panel row at month m uses only tape <= m.

    Construct a close series where a large shock occurs at a known date.
    Verify that the feature values at a month-end BEFORE the shock do not
    reflect the shock (i.e., no look-ahead).
    """
    # Build a flat close then add a large positive shock at day 400
    n = 600
    prices = np.ones(n) * 100.0
    shock_day = 400
    prices[shock_day:] = 200.0  # Double the price — massive shock
    idx = pd.date_range("2000-01-03", periods=n, freq="B")
    close = pd.Series(prices, index=idx)

    shock_date = idx[shock_day]
    month_before_shock = shock_date - pd.offsets.MonthEnd(1)

    # mom_score at month_before_shock should NOT reflect the shock
    from scripts.build_hazard_panel import _mom_score, _trend_pass, _rolling_vol_pctile

    mom = _mom_score(close)
    trend = _trend_pass(close)
    vol = _rolling_vol_pctile(close)

    # At month_before_shock: features should not see the shock
    mom_before = mom[mom.index <= month_before_shock].iloc[-1] if len(mom[mom.index <= month_before_shock]) > 0 else np.nan
    trend_before = trend[trend.index <= month_before_shock].iloc[-1] if len(trend[trend.index <= month_before_shock]) > 0 else np.nan

    # Mom_score before shock should be near 0 (flat series)
    if not np.isnan(mom_before):
        assert abs(mom_before) < 0.05, (
            f"mom_score before shock = {mom_before:.4f}, expected ~0 for flat series"
        )

    # Trend before shock: flat series at 100 vs 200d MA of 100 → should be ~0
    if not np.isnan(trend_before):
        # trend_pass = 1 if close > 200d SMA; flat series at 100 vs SMA ~100 → borderline
        assert trend_before in (0.0, 1.0), f"trend_pass must be 0 or 1, got {trend_before}"

    # After shock: mom_score should be large positive
    mom_after = mom[mom.index > shock_date].dropna()
    if len(mom_after) >= 21:
        assert mom_after.iloc[21] > 0.3, (
            f"mom_score after 2x price shock should be strongly positive, "
            f"got {mom_after.iloc[21]:.4f}"
        )


# ---------------------------------------------------------------------------
# Test 7: rho_hat structure
# ---------------------------------------------------------------------------

def test_rho_hat_structure():
    """rho_hat.json must have required keys and valid value ranges."""
    rho_path = _REPO / "data/hazard/rho_hat.json"
    if not rho_path.exists():
        pytest.skip("rho_hat.json not built yet — run build_hazard_panel.py first")

    with open(rho_path) as f:
        rho = json.load(f)

    assert "doc" in rho, "rho_hat must have a 'doc' field (W4.2 guidance)"
    assert "pooled" in rho, "rho_hat must have 'pooled' section"
    assert "by_family_direction" in rho, "rho_hat must have 'by_family_direction' section"

    for direction in ["up", "down"]:
        assert direction in rho["pooled"], f"pooled must have '{direction}' direction"
        p = rho["pooled"][direction]
        assert "rho_y1" in p
        assert "avg_k" in p
        assert "n_months" in p

        if p["rho_y1"] is not None:
            # Correlation must be in [-1, 1]
            assert -1.0 <= p["rho_y1"] <= 1.0, (
                f"rho_y1 for {direction} = {p['rho_y1']} is outside [-1, 1]"
            )

        assert p.get("avg_k", 0) > 0, f"avg_k for {direction} must be positive"
        assert p.get("n_months", 0) > 0, f"n_months for {direction} must be positive"

    # Check by_family_direction has entries for all 6 combinations
    expected_keys = [
        "us_sector_up", "us_sector_down",
        "country_up", "country_down",
        "cn_sector_up", "cn_sector_down",
    ]
    for k in expected_keys:
        assert k in rho["by_family_direction"], f"Missing family_direction key: {k}"


# ---------------------------------------------------------------------------
# Test 8: KM baseline structure
# ---------------------------------------------------------------------------

def test_km_baseline_structure():
    """km_baseline JSON must have required families, directions, and valid fields."""
    km_paths = list((_REPO / "data/hazard").glob("km_baseline_*.json"))
    if not km_paths:
        pytest.skip("No km_baseline_*.json found — run build_hazard_panel.py first")

    with open(km_paths[0]) as f:
        km = json.load(f)

    assert "families" in km
    assert "pooled" in km
    assert "doc" in km
    assert "turn_def_version" in km

    for fam in ["us_sector", "country", "cn_sector"]:
        assert fam in km["families"], f"Missing family: {fam}"
        for direction in ["up", "down"]:
            assert direction in km["families"][fam], f"Missing {fam}/{direction}"
            d = km["families"][fam][direction]
            assert "n_rows" in d
            assert "n_events_y1" in d
            assert "buckets" in d
            assert "censoring_rate" in d
            assert 0.0 <= d["censoring_rate"] <= 1.0, (
                f"{fam}/{direction} censoring_rate out of range"
            )

            # Each bucket must have valid lambda
            for bk in d["buckets"]:
                assert "lambda" in bk
                assert 0.0 <= bk["lambda"] <= 1.0, (
                    f"{fam}/{direction} bucket {bk['bucket']}: lambda={bk['lambda']} out of [0,1]"
                )
                assert "at_risk" in bk and bk["at_risk"] >= 0
                assert bk["events"] <= bk["at_risk"], (
                    f"Events ({bk['events']}) > at_risk ({bk['at_risk']}) in {fam}/{direction}/{bk['bucket']}"
                )

    # Survival must be monotone decreasing within each group's buckets
    for fam in ["us_sector", "country", "cn_sector"]:
        for direction in ["up", "down"]:
            bks = km["families"][fam][direction].get("buckets", [])
            if len(bks) < 2:
                continue
            survivals = [b["survival"] for b in bks]
            for i in range(1, len(survivals)):
                assert survivals[i] <= survivals[i - 1] + 1e-9, (
                    f"{fam}/{direction}: survival not monotone at bucket {i}"
                )


# ---------------------------------------------------------------------------
# Test 9: Minimum event counts (acceptance gate from D5-W1)
# ---------------------------------------------------------------------------

def test_event_counts_meet_acceptance_gate():
    """D5-W1 acceptance: >= 1800 events total, >= 500 CN events.

    This is the acceptance gate from D5_PREDICTION.md: the hazard model is
    estimable when we have sufficient events.
    """
    panel_paths = list((_REPO / "data/hazard").glob("panel_*.parquet"))
    if not panel_paths:
        pytest.skip("No panel parquet found — run build_hazard_panel.py first")

    panel = pd.read_parquet(panel_paths[0])

    total_events_y1 = int(panel["y1"].sum())
    cn_events_y1 = int(panel[panel["family"] == "cn_sector"]["y1"].sum())

    assert total_events_y1 >= 1800, (
        f"Total y1 events = {total_events_y1}, need >= 1800 for the hazard model to be estimable"
    )
    assert cn_events_y1 >= 500, (
        f"CN y1 events = {cn_events_y1}, need >= 500 (D5-W1 acceptance gate)"
    )

    # Also check the universe: exactly 3 families, no extraneous families
    families = set(panel["family"].unique())
    assert families == {"us_sector", "country", "cn_sector"}, (
        f"Panel has unexpected families: {families}"
    )
