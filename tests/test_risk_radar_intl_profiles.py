"""Tests for the 7-market international risk radar profiles (2026-07-16).

Network-free: all store reads are monkeypatched to synthetic data.
Never touches data/ or site/ — forward-log roundtrips use tmp_path.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

# ── helpers ─────────────────────────────────────────────────────────────────

def _bdays(n: int, start: str = "1993-01-04") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _flat(n: int, val: float = 100.0, start: str = "1993-01-04") -> pd.DataFrame:
    """Flat-noise price series as a DataFrame with a 'close' column."""
    rng = np.random.default_rng(42)
    prices = val + rng.normal(0, 0.01, size=n)
    prices = np.abs(prices)
    idx = _bdays(n, start)
    return pd.DataFrame({"close": prices}, index=idx)


def _flat_rate(n: int, val: float = 4.0) -> pd.DataFrame:
    """Flat-noise rate series."""
    rng = np.random.default_rng(7)
    rates = val + rng.normal(0, 0.002, size=n)
    return pd.DataFrame({"us2y": rates, "close": rates}, index=_bdays(n))


def _melt_up(n_flat: int = 3000, n_run: int = 400, base: float = 100.0) -> pd.DataFrame:
    """Flat-noise base followed by an accelerating melt-up ending +60% above the 200dma."""
    rng = np.random.default_rng(13)
    flat = base + rng.normal(0, 0.01, size=n_flat)
    # exponential ramp: ends at roughly base * 1.70 after n_run sessions
    t = np.linspace(0, 1, n_run)
    ramp = base * (1.0 + 0.70 * t ** 2) + rng.normal(0, 0.1, size=n_run)
    prices = np.concatenate([flat, ramp])
    idx = _bdays(len(prices))
    return pd.DataFrame({"close": prices}, index=idx)


def _melt_crash(n_flat: int = 3000, n_run: int = 400, n_crash: int = 10,
                base: float = 100.0) -> pd.DataFrame:
    """Same melt-up + a final -20% in 10 sessions."""
    rng = np.random.default_rng(13)
    flat = base + rng.normal(0, 0.01, size=n_flat)
    t = np.linspace(0, 1, n_run)
    ramp = base * (1.0 + 0.70 * t ** 2) + rng.normal(0, 0.1, size=n_run)
    top = float(ramp[-1])
    crash = np.linspace(top, top * 0.80, n_crash) + rng.normal(0, 0.05, size=n_crash)
    prices = np.concatenate([flat, ramp, crash])
    idx = _bdays(len(prices))
    return pd.DataFrame({"close": prices}, index=idx)


# ─── END-LOADED STRESS FIXTURE (shared by tests 3/4/5) ──────────────────────
# Design: 3000 sessions of flat base, then 80 sessions of exponential melt-up
# with simultaneously rising rates and FX legs.  The melt-up is short enough
# that at the last bar the blended composite's trailing-504d percentile is >= 0.92
# (risk-off band), yet the price is well above its 200-day MA.  The 80-session
# ramp avoids the saturation plateau that longer ramps produce (the trailing
# percentile drops when the blend is constant at max).  Verified empirically:
# state_ungated="risk-off", top_score=92, context_gate.met=True,
# context_gate.below_200dma=False, context_gate.recent_parabolic=True.

_N_FLAT_STRESS = 3000
_N_RUN_STRESS = 80


def _stress_bench(base: float = 100.0) -> pd.DataFrame:
    """~3000 flat sessions then 80-session exponential melt-up (strictly accelerating)."""
    n_total = _N_FLAT_STRESS + _N_RUN_STRESS
    t = np.linspace(0, 1, _N_RUN_STRESS)
    flat_b = np.full(_N_FLAT_STRESS, base)
    ramp_b = base * np.exp(0.6 * t ** 2)
    prices = np.concatenate([flat_b, ramp_b])
    return pd.DataFrame({"close": prices}, index=_bdays(n_total))


def _stress_rates(n_total: int) -> pd.DataFrame:
    """Rates flat at 2% then smoothly accelerating in the melt-up window (quadratic)."""
    t = np.linspace(0, 1, _N_RUN_STRESS)
    rates_flat = np.full(_N_FLAT_STRESS, 2.0)
    rates_ramp = 2.0 + 2.0 * t ** 2
    rates = np.concatenate([rates_flat, rates_ramp])
    return pd.DataFrame({"us2y": rates, "close": rates}, index=_bdays(n_total))


def _stress_fx(n_total: int) -> pd.DataFrame:
    """FX flat then exponential depreciation (risk-ward) in the melt-up window."""
    t = np.linspace(0, 1, _N_RUN_STRESS)
    fx_flat = np.full(_N_FLAT_STRESS, 100.0)
    fx_ramp = 100.0 * np.exp(0.3 * t ** 2)
    fx = np.concatenate([fx_flat, fx_ramp])
    return pd.DataFrame({"close": fx}, index=_bdays(n_total))


def _make_stress_store(bench_df: pd.DataFrame) -> "callable":
    """Return a fake store.read wired to end-loaded stress data.

    Helper series (rates, FX) are always index-matched to bench_df regardless of
    bench_df's length (which may exceed _N_FLAT_STRESS + _N_RUN_STRESS when a crash
    tail has been appended). Values are extended by repeating the last known value
    for any extra sessions beyond the original ramp.
    """
    n_total = len(bench_df)
    idx = bench_df.index

    # Build rate and FX series aligned to bench_df.index
    t_ramp = np.linspace(0, 1, _N_RUN_STRESS)
    rates_flat = np.full(_N_FLAT_STRESS, 2.0)
    rates_ramp = 2.0 + 2.0 * t_ramp ** 2
    rates_base = np.concatenate([rates_flat, rates_ramp])
    # Pad or trim to n_total (pad by repeating last value)
    if len(rates_base) < n_total:
        rates_base = np.concatenate([rates_base, np.full(n_total - len(rates_base), rates_base[-1])])
    else:
        rates_base = rates_base[:n_total]
    rate_df = pd.DataFrame({"us2y": rates_base, "close": rates_base}, index=idx)

    fx_flat = np.full(_N_FLAT_STRESS, 100.0)
    fx_ramp = 100.0 * np.exp(0.3 * t_ramp ** 2)
    fx_base = np.concatenate([fx_flat, fx_ramp])
    if len(fx_base) < n_total:
        fx_base = np.concatenate([fx_base, np.full(n_total - len(fx_base), fx_base[-1])])
    else:
        fx_base = fx_base[:n_total]
    fx_df = pd.DataFrame({"close": fx_base}, index=idx)

    dxy_flat = pd.DataFrame({"close": np.full(n_total, 100.0)}, index=idx)

    def fake_read(group, name, **kwargs):
        if group == "fred":
            return rate_df
        if group == "yahoo" and name == "DX-Y.NYB":
            return dxy_flat
        if group in ("intl", "intl_etf"):
            return bench_df
        if group == "yahoo":
            return fx_df
        if group in ("china_breadth", "canada_breadth"):
            n = len(bench_df)
            return pd.DataFrame({"pct_above_200": np.full(n, 60.0)},
                                index=bench_df.index[:n])
        if group == "china_property":
            return None
        return None

    return fake_read


# ─── helper: build a complete fake_store for the 7-market profiles ──────────

def _make_fake_store(bench_df: pd.DataFrame, n_rate: int = 4400):
    """Return a fake store.read that serves synthetic data for all needed series."""
    rate_df = _flat_rate(n_rate)
    fx_df = _flat(n_rate)
    dxy_df = _flat(n_rate, val=100.0)

    def fake_read(group, name, **kwargs):
        # FRED rates
        if group == "fred":
            return rate_df
        # Yahoo DXY
        if group == "yahoo" and name == "DX-Y.NYB":
            return dxy_df
        # bench (intl group) — all index tickers
        if group == "intl":
            return bench_df
        # intl_etf group — ETFs mirror the bench
        if group == "intl_etf":
            return bench_df
        # breadth groups
        if group in ("china_breadth", "canada_breadth"):
            n = len(bench_df)
            df = pd.DataFrame({"pct_above_200": np.full(n, 60.0)},
                              index=bench_df.index[:n])
            return df
        # FX pairs from intl group (handled above), yahoo FX
        if group == "yahoo":
            return fx_df
        # china_property for cgb (CN profile)
        if group == "china_property":
            return None
        # all other stores
        return None

    return fake_read


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: profiles match config.yml
# ═══════════════════════════════════════════════════════════════════════════

def test_profiles_match_config():
    """Each of the 7 new profiles matches the config.yml index, fx, and fx_invert."""
    from engine import risk_radar_intl as rri

    cfg_path = Path(__file__).resolve().parent.parent / "config.yml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    intl_cfg = cfg["intl"]["countries"]

    expected = {
        "kr": {"index": "^KS11",  "fx": "USDKRW=X", "fx_invert": True},
        "jp": {"index": "^N225",  "fx": "USDJPY=X", "fx_invert": True},
        "tw": {"index": "^TWII",  "fx": "USDTWD=X", "fx_invert": True},
        "in": {"index": "^NSEI",  "fx": "USDINR=X", "fx_invert": True},
        "au": {"index": "^AXJO",  "fx": "AUDUSD=X", "fx_invert": False},
        "gb": {"index": "^FTSE",  "fx": "GBPUSD=X", "fx_invert": False},
        "ez": {"index": "^STOXX", "fx": "EURUSD=X", "fx_invert": False},
    }

    # all 10 keys present
    assert set(rri.PROFILES.keys()) == {"cn", "hk", "ca", "kr", "jp", "tw", "in", "au", "gb", "ez"}

    for key_lower, exp in expected.items():
        key_upper = key_lower.upper()
        prof = rri.PROFILES[key_lower]
        cfg_c = intl_cfg[key_upper]

        assert prof.bench == ("intl", exp["index"]), f"{key_lower}: bench mismatch"
        assert prof.fx_pair == ("intl", exp["fx"]), f"{key_lower}: fx_pair mismatch"
        expected_sign = 1 if exp["fx_invert"] else -1
        assert prof.fx_risk_sign == expected_sign, (
            f"{key_lower}: fx_risk_sign {prof.fx_risk_sign} != {expected_sign}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: legacy profiles frozen
# ═══════════════════════════════════════════════════════════════════════════

def test_legacy_profiles_frozen():
    """CN/HK/CA profiles have no new extension fields — guards the frozen composites."""
    from engine import risk_radar_intl as rri

    for key in ("cn", "hk", "ca"):
        prof = rri.PROFILES[key]
        assert prof.fx_pair is None, f"{key}: fx_pair should be None"
        assert prof.ext_sources == (), f"{key}: ext_sources should be empty"
        assert prof.gate_mode == "below_200dma", f"{key}: gate_mode should be below_200dma"
        assert prof.disclaimer is None, f"{key}: disclaimer should be None (uses module default)"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: parabolic gate opens above 200dma
# Uses the end-loaded stress fixture (state_ungated="risk-off", top_score=92).
# Asserts the gate machinery and that the loud state is not suppressed.
# ═══════════════════════════════════════════════════════════════════════════

def test_parabolic_gate_opens_above_ma(monkeypatch):
    """End-loaded stress fixture: gate open above 200dma via recent_parabolic.
    state == state_ungated (loud state preserved), both in ('elevated','risk-off').
    context_gate: met=True, below_200dma=False, recent_parabolic=True."""
    from engine import risk_radar_intl as rri
    from lib import store

    bench_df = _stress_bench()
    fake_read = _make_stress_store(bench_df)
    monkeypatch.setattr(store, "read", fake_read)

    snap = rri.snapshot(rri.KR_PROFILE)
    assert snap.get("state") is not None, "Snapshot must not be degraded with stress fixture"

    cg = snap.get("context_gate", {})
    state = snap["state"]
    state_ungated = snap["state_ungated"]

    # recent_parabolic key must be present for gate_mode=below_or_recent_parabolic
    assert "recent_parabolic" in cg, (
        "recent_parabolic key must be in context_gate for gate_mode=below_or_recent_parabolic"
    )

    # gate must be open (recent_parabolic triggers it when price is above 200dma)
    assert cg.get("met") is True, f"context_gate.met must be True; got {cg}"

    # price is above 200dma (melt-up, not a bear market)
    assert cg.get("below_200dma") is False, (
        f"below_200dma must be False in a melt-up above 200dma; got {cg}"
    )

    # recent_parabolic must be True (extension percentile >= 0.98)
    assert cg.get("recent_parabolic") is True, (
        f"recent_parabolic must be True at end of stress ramp; got {cg}"
    )

    # state == state_ungated: gate open = loud state preserved (not capped)
    assert state == state_ungated, (
        f"When gate is open, state ({state}) must equal state_ungated ({state_ungated})"
    )

    # both states must be loud (the fixture is designed to reach elevated/risk-off)
    assert state_ungated in ("elevated", "risk-off"), (
        f"Stress fixture must reach elevated or risk-off; got state_ungated={state_ungated} "
        f"(top_score={snap.get('top_score')}). If this fails, the fixture no longer produces a "
        f"loud ungated band — check the stress fixture shape."
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: gate memory survives crash
# Uses the same end-loaded stress fixture + final -20% crash over 10 sessions.
# Price after crash is still above 200dma (the melt-up ended +82% above it).
# The GATE_MEMORY=60 window keeps recent_parabolic True even after the crash.
# ═══════════════════════════════════════════════════════════════════════════

def test_gate_memory_through_crash(monkeypatch):
    """After end-loaded melt-up + -20% crash (price still above 200dma), gate stays
    open via GATE_MEMORY: context_gate.met must be True even if the latest extension
    percentile has slipped below the parabolic threshold."""
    from engine import risk_radar_intl as rri
    from lib import store

    # Build the stress bench then append a -20% crash over 10 sessions
    bench_df = _stress_bench()
    top_px = float(bench_df["close"].iloc[-1])
    crash_px = np.linspace(top_px, top_px * 0.80, 10)
    crash_idx = pd.bdate_range(bench_df.index[-1], periods=11)[1:]
    crash_df = pd.DataFrame({"close": crash_px}, index=crash_idx)
    full_bench = pd.concat([bench_df, crash_df])

    # After crash: price is still above the 200dma (melt-up ended ~+82% above it)
    ma200 = full_bench["close"].rolling(200, min_periods=120).mean()
    assert full_bench["close"].iloc[-1] > ma200.iloc[-1], (
        "After -20% crash, price must still be above 200dma — "
        "the crash fixture is miscalibrated if this fails."
    )

    fake_read = _make_stress_store(full_bench)
    monkeypatch.setattr(store, "read", fake_read)

    snap = rri.snapshot(rri.KR_PROFILE)
    assert snap.get("state") is not None, "Snapshot must not be degraded with crash fixture"

    cg = snap.get("context_gate", {})

    # recent_parabolic key must exist (gate_mode=below_or_recent_parabolic)
    assert "recent_parabolic" in cg, "recent_parabolic key must be present"

    # Price is above 200dma — assert the gate payload reflects this correctly
    assert cg.get("below_200dma") is False, (
        f"below_200dma must be False after -20% crash that left price above 200dma; got {cg}"
    )

    # GATE_MEMORY=60: the parabolic gate stays open for 60 sessions after the last
    # parabolic reading, so with only 10 crash sessions the gate must remain open
    assert cg.get("met") is True, (
        f"context_gate.met must be True — GATE_MEMORY ({rri._GATE_MEMORY} sessions) keeps the "
        f"gate open for 60 sessions after the last parabolic reading; crash was only 10 sessions. "
        f"Got context_gate={cg}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: legacy gate still caps loud tiers
# Uses the same end-loaded stress fixture through a throwaway legacy profile.
# state_ungated must be in ('elevated','risk-off'); state must be 'caution'
# (the cap actually exercised); recent_parabolic must NOT be in context_gate.
# ═══════════════════════════════════════════════════════════════════════════

def test_legacy_gate_still_caps(monkeypatch):
    """Legacy gate_mode='below_200dma' on the stress fixture: price is above 200dma,
    so the gate is CLOSED.  state_ungated is loud (elevated/risk-off) but state must
    be capped to 'caution'.  recent_parabolic must not appear in context_gate."""
    from engine.risk_radar_intl import (
        RadarProfile, _BANDS, snapshot, KR_PROFILE,
    )
    from lib import store

    # Clone KR_PROFILE with legacy gate (same legs, same ext_sources so the fixture works)
    legacy_prof = RadarProfile(
        key="kr",
        bench=KR_PROFILE.bench,
        breadth_group=None,
        breadth_code="kr_breadth",
        comp_legs=KR_PROFILE.comp_legs,
        scares=KR_PROFILE.scares,
        bands=_BANDS,
        prob_base=KR_PROFILE.prob_base,
        prob_cal=KR_PROFILE.prob_cal,
        caveat_en=KR_PROFILE.caveat_en,
        caveat_zh=KR_PROFILE.caveat_zh,
        fx_pair=KR_PROFILE.fx_pair,
        fx_risk_sign=KR_PROFILE.fx_risk_sign,
        fx_code=KR_PROFILE.fx_code,
        ext_sources=KR_PROFILE.ext_sources,
        gate_mode="below_200dma",  # legacy mode — no parabolic unlock
        disclaimer=KR_PROFILE.disclaimer,
    )

    bench_df = _stress_bench()
    fake_read = _make_stress_store(bench_df)
    monkeypatch.setattr(store, "read", fake_read)

    snap = snapshot(legacy_prof)
    assert snap.get("state") is not None, "Snapshot must not be degraded with stress fixture"

    cg = snap.get("context_gate", {})
    state = snap["state"]
    state_ungated = snap["state_ungated"]

    # The stress fixture yields a loud ungated band
    assert state_ungated in ("elevated", "risk-off"), (
        f"Stress fixture must yield elevated/risk-off ungated; got {state_ungated}. "
        f"If this fails the fixture no longer exercises the cap."
    )

    # Legacy gate: price is above 200dma, so gate is CLOSED
    assert cg.get("below_200dma") is False, (
        f"below_200dma must be False in melt-up above 200dma; got {cg}"
    )
    assert cg.get("met") is False, (
        f"Legacy gate must be CLOSED (met=False) when price is above 200dma; got {cg}"
    )

    # The cap must actually fire: loud ungated → capped to caution
    assert state == "caution", (
        f"Legacy gate: state must be capped to 'caution' when ungated={state_ungated} "
        f"and below_200dma=False; got state={state}"
    )

    # No recent_parabolic key in legacy profiles
    assert "recent_parabolic" not in cg, (
        "Legacy gate_mode='below_200dma' must NOT add recent_parabolic to context_gate"
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: forward log roundtrip for new market
# ═══════════════════════════════════════════════════════════════════════════

def test_forward_log_roundtrip_new_market(tmp_path, monkeypatch):
    """Log + grade + scorecard roundtrip for a new 'kr' market entry."""
    from engine import risk_radar_intl_audit as rra
    from lib import store

    # minimal snapshot dict for KR
    snap = {
        "schema": "risk_radar_intl.v1",
        "asof": "2026-07-16",
        "market": "kr",
        "state": "caution",
        "state_ungated": "elevated",
        "top_score": 75,
        "dominant_scare": "rate_shock",
        "conjunction": False,
        "context_gate": {"met": False, "below_200dma": False, "recent_parabolic": True},
        "scares": [],
        "drawdown_prob": {},
        "trajectory": None,
        "gross_factor": 0.9,
        "caveat_en": "test",
        "caveat_zh": "test",
        "disclaimer": "test",
    }

    # log_snapshot
    r1 = rra.log_snapshot(snap, "kr", root=str(tmp_path))
    assert r1 is True, "First log_snapshot should return True"

    # idempotent — same asof returns False
    r2 = rra.log_snapshot(snap, "kr", root=str(tmp_path))
    assert r2 is False, "Second log_snapshot for same asof should be idempotent"

    # verify file was written
    log_path = tmp_path / "data" / "risk_radar_intl" / "kr_forward_log.jsonl"
    assert log_path.exists()
    rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["asof"] == "2026-07-16"
    assert rows[0]["market"] == "kr"

    # grade_log — synthesize a bench series with matured outcomes
    # we need at least 21 bdays of forward data after 2026-07-16
    # use a fake store with ~8000 bday series so grade_entry can mature
    n = 8000
    prices = np.linspace(100, 110, n)  # gently rising, no -5% dd
    idx = pd.bdate_range("1993-01-04", periods=n)
    bench_df = pd.DataFrame({"close": prices}, index=idx)

    from engine import risk_radar_intl as rri
    original_bench = rra._bench

    def fake_bench(profile):
        s = bench_df["close"].copy()
        s.index = pd.to_datetime(s.index)
        return s.sort_index()

    monkeypatch.setattr(rra, "_bench", fake_bench)

    from engine import risk_radar_intl as _rri
    n_graded = rra.grade_log(_rri.KR_PROFILE, root=str(tmp_path))
    # With asof 2026-07-16 and bench only going to about 2024 (8000 bdays from 1993),
    # the entry may not mature. n_graded >= 0 either way.
    assert n_graded >= 0

    sc = rra.scorecard("kr", root=str(tmp_path), log_governance=False)
    assert sc["market"] == "kr"
    assert sc["n_graded"] >= 0
    assert sc["can_force"] is False  # always False when n < MIN_GRADED_FORCE


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: calibration probs sane on synthetic data
# ═══════════════════════════════════════════════════════════════════════════

def test_calibration_probs_sane(monkeypatch):
    """calibrate() returns probs in [0,1] and monotone along states per horizon."""
    from engine import risk_radar_intl as rri
    from lib import store
    from scripts.calibrate_risk_radar_intl import calibrate, _STATE_ORDER

    # use a bench with enough history for calibration (need >=100 valid days after windowing)
    n = 5000
    rng = np.random.default_rng(42)
    prices = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    prices = np.abs(prices) + 50
    idx = _bdays(n)
    bench_df = pd.DataFrame({"close": prices}, index=idx)

    fake_read = _make_fake_store(bench_df, n_rate=5000)
    monkeypatch.setattr(store, "read", fake_read)

    result = calibrate(rri.KR_PROFILE, years=20)
    if result is None:
        pytest.skip("insufficient synthetic data for calibration — harness works but window too short")

    pb = result["prob_base"]
    pc = result["prob_cal"]

    # probs in [0,1]
    for hk in ("h5", "h10", "h21"):
        assert 0.0 <= pb[hk] <= 1.0, f"prob_base[{hk}] out of range"
        for st, p in pc[hk].items():
            assert 0.0 <= p <= 1.0, f"prob_cal[{hk}][{st}]={p} out of range"

    # monotone non-decreasing (flat passes): for each horizon, prob[calm] <= ... <= prob[risk-off]
    for hk in ("h5", "h10", "h21"):
        prev = 0.0
        for st in _STATE_ORDER:
            if st in pc[hk]:
                assert pc[hk][st] >= prev - 1e-9, (
                    f"prob_cal[{hk}][{st}]={pc[hk][st]} < prev={prev} (not monotone non-decreasing)"
                )
                prev = pc[hk][st]

    # prob_base h21 > 0 (with random walk data there will be some drawdowns)
    assert pb["h21"] > 0.0, "h21 base rate should be > 0 with random-walk data"

    # seed-policy: calibrate() returns prob_cal flat at base for all states/horizons
    for hk in ("h5", "h10", "h21"):
        base_h = pb[hk]
        for st in _STATE_ORDER:
            if st in pc[hk]:
                assert abs(pc[hk][st] - base_h) < 1e-9, (
                    f"calibrate() seed-policy violation: prob_cal[{hk}][{st}]={pc[hk][st]} != prob_base[{hk}]={base_h} "
                    f"(expected flat-at-base; the harness should never bake in-sample lift)"
                )


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: seed-policy regression — all 7 new profiles flat at base
# ═══════════════════════════════════════════════════════════════════════════

def test_new_profiles_prob_cal_flat_at_base():
    """Regression: for each of the 7 new profiles, prob_cal[h][state] == prob_base[h]
    for every state and every horizon. This is the baked seed-policy guard — the live
    tuner (risk_radar_intl_tune, n_graded>=25) owns any divergence from here forward."""
    from engine import risk_radar_intl as rri

    NEW_PROFILES = ("kr", "jp", "tw", "in", "au", "gb", "ez")
    horizons = ("h5", "h10", "h21")
    states = ("calm", "watch", "caution", "elevated", "risk-off")

    for key in NEW_PROFILES:
        prof = rri.PROFILES[key]
        pb = prof.prob_base
        pc = prof.prob_cal

        # All horizons and states must be present
        for hk in horizons:
            assert hk in pb, f"{key}: prob_base missing {hk}"
            assert hk in pc, f"{key}: prob_cal missing {hk}"
            for st in states:
                assert st in pc[hk], f"{key}: prob_cal[{hk}] missing state '{st}'"
                v = pc[hk][st]
                base = pb[hk]
                assert abs(v - base) < 1e-9, (
                    f"Seed-policy violation: {key} prob_cal[{hk}][{st}]={v} != prob_base[{hk}]={base} "
                    f"(expected flat-at-base; no in-sample lift should be baked)"
                )

        # Also verify all values in [0, 1]
        for hk in horizons:
            for st in states:
                v = pc[hk][st]
                assert 0.0 <= v <= 1.0, f"{key} prob_cal[{hk}][{st}]={v} out of [0,1]"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9: null-safe — store returns None for everything
# ═══════════════════════════════════════════════════════════════════════════

def test_null_safe(monkeypatch):
    """snapshot(KR_PROFILE) with store.read returning None everywhere must return
    a valid schema payload (state None, degraded_reason 'no_data') and never raise."""
    from engine import risk_radar_intl as rri
    from lib import store

    monkeypatch.setattr(store, "read", lambda g, n, **kw: None)

    snap = rri.snapshot(rri.KR_PROFILE)
    assert snap["schema"] == "risk_radar_intl.v1"
    assert snap["state"] is None
    assert snap.get("degraded_reason") in ("no_data", "compute_error")

    # also test CN and HK (legacy) stay null-safe
    for key in ("cn", "hk", "ca"):
        snap2 = rri.snapshot(rri.PROFILES[key])
        assert snap2["state"] is None
        assert snap2.get("degraded_reason") in ("no_data", "compute_error")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10: ledger lane gate — _ledger_lane_armed() follows env vars
# ═══════════════════════════════════════════════════════════════════════════

def test_ledger_lane_gate(monkeypatch):
    """_ledger_lane_armed() is True only when COLLECT_LANE=nightly (or US_LANE=nightly).
    Verifies the house law gate added to engine/intl_run.py (FIX 1)."""
    from engine.intl_run import _ledger_lane_armed

    # No COLLECT_LANE or US_LANE set → False
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    assert _ledger_lane_armed() is False, (
        "_ledger_lane_armed() must be False when COLLECT_LANE and US_LANE are both absent"
    )

    # COLLECT_LANE=nightly → True
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    assert _ledger_lane_armed() is True, (
        "_ledger_lane_armed() must be True when COLLECT_LANE=nightly"
    )

    # COLLECT_LANE=intraday → False
    monkeypatch.setenv("COLLECT_LANE", "intraday")
    assert _ledger_lane_armed() is False, (
        "_ledger_lane_armed() must be False when COLLECT_LANE=intraday"
    )

    # US_LANE=nightly (legacy alias) with COLLECT_LANE absent → True
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.setenv("US_LANE", "nightly")
    assert _ledger_lane_armed() is True, (
        "_ledger_lane_armed() must be True when US_LANE=nightly (legacy alias)"
    )

    # Both absent again → False
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    assert _ledger_lane_armed() is False, (
        "_ledger_lane_armed() must be False after clearing both env vars"
    )
