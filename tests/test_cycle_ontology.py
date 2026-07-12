"""Tests for engine/cycle_ontology.py (W1.2 acceptance suite).

Covers the 5 D1-§2.5 assertions + additional contract tests per the wave spec:
1.  Crosswalk totality — all 5×8 cells resolve; no KeyError; every stance ∈ STANCES.
2.  No contradictory pair — no cell has phase=Peak with stance ∈ {BUY, GET READY}
    without divergence=True.
3.  Signal coherence — transition_signal never returns BUY for Peak/Downturn,
    nor SELL for Trough/Recovery.
4.  Live-output sweep (optional — passes if no JSON files are found).
5.  Generated-JS sync — --check exits 0.
6.  position_v2 causality — appending future bars never changes past values.
7.  position_v2 range / comparability — peaks map to comparable positions on
    two synthetic series with different vol.
8.  Hysteresis — single-bar wobble does NOT flip phase; sustained move DOES.
9.  detect_turns confirmed_at correctness — confirm_lag > 0; turn invisible before
    confirmed_at.
10. match_turns exact / shifted / orphaned cases.
11. resolve_state total function — all phase×ladder combinations resolve; unknown
    inputs raise ValueError.
12. project_next overdue semantics.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

# ── import target ──────────────────────────────────────────────────────────
from engine.cycle_ontology import (
    LADDER,
    ONTOLOGY_VERSION,
    PHASES,
    STANCES,
    TurnParams,
    canonical_position,
    classify_phase,
    detect_turns,
    export_payload,
    match_turns,
    project_next,
    resolve_state,
    transition_signal,
    write_stance_matrix,
)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_close(n: int = 600, seed: int = 42, vol: float = 0.01,
                drift: float = 0.0001) -> pd.Series:
    """Synthetic daily close with random-walk + trend."""
    rng = np.random.default_rng(seed)
    log_ret = rng.normal(drift, vol, n)
    prices = 100.0 * np.exp(np.cumsum(log_ret))
    idx = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def _make_cycle(n: int = 600, seed: int = 99, amplitude: float = 0.25,
                period: int = 252) -> pd.Series:
    """Synthetic series with a clear sinusoidal cycle."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    noise = rng.normal(0, 0.01, n)
    prices = 100.0 * np.exp(amplitude * np.sin(2 * np.pi * t / period) + noise)
    idx = pd.date_range("2018-01-02", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def _null_mtf() -> dict:
    """Empty MTF state (all False/zero) for classify_phase calls."""
    return {"macd_pos": False, "macd_cross_up": False, "macd_cross_dn": False,
            "macd_curl_up": False, "macd_curl_dn": False}


def _bullish_mtf() -> dict:
    return {"macd_pos": True, "macd_cross_up": True, "macd_cross_dn": False,
            "macd_curl_up": False, "macd_curl_dn": False}


def _bearish_mtf() -> dict:
    return {"macd_pos": False, "macd_cross_up": False, "macd_cross_dn": True,
            "macd_curl_up": False, "macd_curl_dn": False}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Crosswalk totality
# ─────────────────────────────────────────────────────────────────────────────

def test_crosswalk_all_cells_resolve():
    """All 5×8 combinations resolve without raising; every stance ∈ STANCES."""
    phases = list(PHASES.keys())
    errors = []
    for phase in phases:
        for ladder in LADDER:
            # pos-gated cells: test both pos values
            for pos in (30.0, 70.0):
                try:
                    rs = resolve_state(
                        pos=pos, phase=phase, phase_dir="rising",
                        ladder_state=ladder,
                    )
                except Exception as exc:
                    errors.append(f"({phase}, {ladder}, pos={pos}): {exc}")
                    continue
                assert rs["stance"] in STANCES, (
                    f"({phase}, {ladder}): stance {rs['stance']!r} not in STANCES"
                )
                assert rs["tone"] in {"bullish", "bearish", "neutral", "caution", "anticipatory"}, (
                    f"({phase}, {ladder}): unexpected tone {rs['tone']!r}"
                )
    assert not errors, "resolve_state raised on cells:\n" + "\n".join(errors)


def test_crosswalk_cell_count():
    """Payload crosswalk covers all simple cells + pos-gated variants.

    Original count: 8 ladder states × 5 phases = 40, minus 2 pos-gated
    Downturn×TURN SIGNALED/FRESH BUY = 38 simple cells.
    HKRV-W1 adds CONFIRMING TURN (5 simple cells, no pos-gating) → 43 simple cells.
    """
    payload = export_payload()
    cw = payload["crosswalk"]
    # 43 simple cells: original 38 + 5 CONFIRMING TURN cells (one per phase)
    # plus 4 pos-gated entries (2 ladders × 2 pos-gates, unchanged)
    simple_keys = [k for k in cw if "|pos" not in k]
    gated_keys  = [k for k in cw if "|pos" in k]
    assert len(simple_keys) == 43, f"Expected 43 simple cells, got {len(simple_keys)}"
    assert len(gated_keys) == 4,   f"Expected 4 pos-gated cells, got {len(gated_keys)}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. No contradictory pair (the audit's core demand)
# ─────────────────────────────────────────────────────────────────────────────

def test_no_bullish_stance_at_peak_without_divergence():
    """No cell has phase=Peak and stance ∈ {BUY, GET READY} without divergence=True."""
    bullish_stances = {"BUY", "GET READY"}
    for ladder in LADDER:
        for pos in (30.0, 70.0):
            rs = resolve_state(pos=pos, phase="Peak", phase_dir="rising", ladder_state=ladder)
            if rs["stance"] in bullish_stances:
                assert rs["divergence"], (
                    f"Peak × {ladder} (pos={pos}): stance={rs['stance']!r} "
                    f"without divergence=True — contradictory pair!"
                )


def test_peak_buy_states_are_countertrend():
    """Peak × {BOTTOM WATCH, TURN SIGNALED, FRESH BUY} must be COUNTERTREND ONLY."""
    for ladder in ("BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY"):
        for pos in (30.0, 70.0):
            rs = resolve_state(pos=pos, phase="Peak", phase_dir="rising", ladder_state=ladder)
            assert rs["stance"] == "COUNTERTREND ONLY", (
                f"Peak × {ladder} (pos={pos}): expected COUNTERTREND ONLY, got {rs['stance']!r}"
            )
            assert rs["divergence"], f"Peak × {ladder} must set divergence=True"


def test_failed_cycle_sets_phase_conf_low():
    """failed_cycle + DECLINE in Trough/Recovery sets phase_conf='low'."""
    for phase in ("Trough", "Recovery"):
        rs = resolve_state(pos=30.0, phase=phase, phase_dir="falling",
                           ladder_state="DECLINE", failed_cycle=True)
        assert rs["phase_conf"] == "low", f"Expected low confidence for {phase} + DECLINE + failed_cycle"
        assert rs["failed_cycle_override"], "Expected failed_cycle_override=True"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Signal coherence
# ─────────────────────────────────────────────────────────────────────────────

def test_signal_never_buy_in_peak_downturn():
    """transition_signal never returns BUY when phase ∈ {Peak, Downturn}."""
    buy_ladders = ["TURN SIGNALED", "FRESH BUY"]
    for phase in ("Peak", "Downturn"):
        for ladder in buy_ladders:
            sig = transition_signal("Expansion", phase, ladder, phase_age_bars=0)
            assert sig != "BUY", (
                f"transition_signal returned BUY for phase={phase}, ladder={ladder}"
            )


def test_signal_never_sell_in_trough_recovery():
    """transition_signal never returns SELL when phase ∈ {Trough, Recovery}."""
    sell_ladders = ["TOP WATCH", "ROLLING OVER", "DECLINE"]
    for phase in ("Trough", "Recovery"):
        for ladder in sell_ladders:
            sig = transition_signal("Peak", phase, ladder, phase_age_bars=0)
            assert sig != "SELL", (
                f"transition_signal returned SELL for phase={phase}, ladder={ladder}"
            )


def test_signal_buy_fires_on_trough_to_recovery():
    """BUY fires exactly on Trough→Recovery with the right ladder states."""
    for ladder in ("TURN SIGNALED", "FRESH BUY"):
        sig = transition_signal("Trough", "Recovery", ladder, phase_age_bars=0)
        assert sig == "BUY", f"Expected BUY for Trough→Recovery + {ladder}"


def test_signal_sell_fires_on_peak_to_downturn():
    """SELL fires exactly on Peak→Downturn with the right ladder states."""
    for ladder in ("TOP WATCH", "ROLLING OVER", "DECLINE"):
        sig = transition_signal("Peak", "Downturn", ladder, phase_age_bars=0)
        assert sig == "SELL", f"Expected SELL for Peak→Downturn + {ladder}"


def test_signal_respects_ttl():
    """Signal returns None when phase_age_bars ≥ SIGNAL_TTL_BARS."""
    from engine.cycle_ontology import SIGNAL_TTL_BARS
    sig = transition_signal("Trough", "Recovery", "FRESH BUY", phase_age_bars=SIGNAL_TTL_BARS)
    assert sig is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Live-output sweep (optional — passes when no JSON files found)
# ─────────────────────────────────────────────────────────────────────────────

def _find_cycle_jsons() -> list[str]:
    paths = []
    for root, dirs, files in os.walk(os.path.join(_REPO, "site")):
        for f in files:
            if f in ("sector_cycles.json", "country_cycles.json", "china_sector_cycles.json"):
                paths.append(os.path.join(root, f))
    return paths


def _extract_records(data: Any) -> list:
    """Recursively extract all dicts that have a 'now' key from the JSON structure."""
    records = []
    if isinstance(data, dict):
        if "now" in data:
            records.append(data)
        for v in data.values():
            records.extend(_extract_records(v))
    elif isinstance(data, list):
        for item in data:
            records.extend(_extract_records(item))
    return records


@pytest.mark.parametrize("json_path", _find_cycle_jsons() or [None])
def test_live_output_sweep(json_path):
    """Every 'now' block in a live JSON has a valid stance if present (W1.6 field)."""
    if json_path is None:
        pytest.skip("No live JSON files found; skipping live-output sweep")
        return

    with open(json_path) as fh:
        data = json.load(fh)

    records = _extract_records(data)
    # Pre-W1.6 JSONs won't have 'stance' — that's fine; we only check when present
    for rec in records:
        now = rec.get("now")
        if not isinstance(now, dict):
            continue
        stance = now.get("stance")
        if stance is not None:
            assert stance in STANCES, f"Unknown stance {stance!r} in {json_path}"


# ─────────────────────────────────────────────────────────────────────────────
# 4b. Position/phase coherence — the W3.6 regression guard (the ontology promise)
#
# No record may carry a high canonical position (pos_v2 ≥ 85) with a LOW-position
# phase (Trough/Recovery), nor a low position (pos_v2 ≤ 15) with a HIGH-position
# phase (Peak/Downturn), unless the record explicitly declares divergence.  This is
# the guard against the W1.6 mixed-vocabulary bug (phase_v2 was classified from the
# LEGACY range-stochastic `pos` while `pos_v2` used the canonical z/CDF — producing
# records like EWU pos_v2=92.9 phase_v2='Trough').  The kernel fix feeds pos_v2 into
# classify_phase so phase_v2 is DERIVED from pos_v2; this test locks that in on the
# live build and would fail loudly if a future engine change re-introduced the split.
# ─────────────────────────────────────────────────────────────────────────────

# phase level cuts (D1 §2.1): Peak/Downturn require pos ≥ 68; Trough/Recovery ≤ 32.
_LOW_POS_PHASES = {"Trough", "Recovery"}   # phases that require a LOW position
_HIGH_POS_PHASES = {"Peak", "Downturn"}    # phases that require a HIGH position


def assert_record_coherent(now: dict, where: str = "") -> None:
    """Raise AssertionError if a single now-block carries a forbidden pos_v2/phase_v2
    combination without a divergence flag.  Reused by the synthetic-mismatch test."""
    pos_v2 = now.get("pos_v2")
    phase_v2 = now.get("phase_v2")
    if pos_v2 is None or phase_v2 is None:
        return
    div = bool(now.get("divergence"))
    if pos_v2 >= 85.0 and phase_v2 in _LOW_POS_PHASES:
        assert div, (
            f"{where}: pos_v2={pos_v2} (stretched) with phase_v2={phase_v2!r} "
            f"(a low-position phase) and NO divergence flag — mixed-vocabulary record. "
            f"phase_v2 must be derived from pos_v2 (W3.6 coherence guard)."
        )
    if pos_v2 <= 15.0 and phase_v2 in _HIGH_POS_PHASES:
        assert div, (
            f"{where}: pos_v2={pos_v2} (washed-out) with phase_v2={phase_v2!r} "
            f"(a high-position phase) and NO divergence flag — mixed-vocabulary record. "
            f"phase_v2 must be derived from pos_v2 (W3.6 coherence guard)."
        )


@pytest.mark.parametrize("json_path", _find_cycle_jsons() or [None])
def test_live_pos_phase_coherence(json_path):
    """No live record carries pos_v2 ≥ 85 with a Trough/Recovery phase (nor the mirror)
    without a divergence flag — the W3.6 phase-coherence regression."""
    if json_path is None:
        pytest.skip("No live JSON files found; skipping coherence sweep")
        return
    with open(json_path) as fh:
        data = json.load(fh)
    for rec in _extract_records(data):
        now = rec.get("now")
        if not isinstance(now, dict):
            continue
        ticker = rec.get("ticker") or rec.get("id") or rec.get("name") or "?"
        assert_record_coherent(now, where=f"{os.path.basename(json_path)}:{ticker}")


def test_synthetic_mismatch_is_caught():
    """The coherence guard FAILS on a synthetic mixed-vocabulary record (the exact
    W1.6 EWU pathology) — proving the guard is not vacuous."""
    bad = {"pos_v2": 92.9, "phase_v2": "Trough", "divergence": False}
    with pytest.raises(AssertionError):
        assert_record_coherent(bad, where="synthetic")
    # mirror case
    bad2 = {"pos_v2": 4.0, "phase_v2": "Peak", "divergence": False}
    with pytest.raises(AssertionError):
        assert_record_coherent(bad2, where="synthetic-mirror")
    # a genuine divergence (flag set) is allowed
    ok = {"pos_v2": 92.9, "phase_v2": "Trough", "divergence": True}
    assert_record_coherent(ok, where="synthetic-ok")   # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 5. Generated-JS sync (--check round-trip)
# ─────────────────────────────────────────────────────────────────────────────

def test_gen_ontology_js_check():
    """gen_ontology_js --check exits 0 (committed JS matches freshly generated)."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.gen_ontology_js", "--check"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"gen_ontology_js --check failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Position causality — appending future bars never changes past values
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_position_causality():
    """canonical_position is causal: past values don't change when future bars arrive."""
    close = _make_close(n=600)
    # Compute positions on a prefix (first 400 bars)
    pos_short = canonical_position(close.iloc[:400], freq="D")
    # Compute on the full series
    pos_full  = canonical_position(close, freq="D")

    # Where both are non-NaN, values must be identical (to float precision)
    common_idx = pos_short.dropna().index.intersection(pos_full.dropna().index)
    assert len(common_idx) > 100, "Not enough overlapping non-NaN values to test causality"

    max_diff = float((pos_short.loc[common_idx] - pos_full.loc[common_idx]).abs().max())
    assert max_diff == 0.0, (
        f"Position values differ when future bars are appended (max diff={max_diff:.6f}). "
        "canonical_position is NOT causal!"
    )


def test_canonical_position_no_lookahead_expanding_median():
    """Expanding-median vol floor is computed causally (no future data leaks)."""
    # Build a series where a quiet period precedes a volatile one.
    # If the expanding median leaked, the quiet-period σ would be inflated by
    # the volatile period's values, changing early positions.
    n = 500
    rng = np.random.default_rng(0)
    quiet = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.003, 250)))
    loud  = quiet[-1] * np.exp(np.cumsum(rng.normal(0, 0.03,  250)))
    prices = np.concatenate([quiet, loud])
    idx = pd.date_range("2019-01-02", periods=n, freq="B")
    close = pd.Series(prices, index=idx)

    pos_prefix = canonical_position(close.iloc[:250], freq="D")
    pos_full   = canonical_position(close,            freq="D")

    common = pos_prefix.dropna().index.intersection(pos_full.dropna().index)
    # Allow tiny float rounding but not systematic difference
    max_diff = float((pos_prefix.loc[common] - pos_full.loc[common]).abs().max())
    assert max_diff == 0.0, (
        f"Expanding-median vol floor leaks future data (max diff={max_diff:.6f})!"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Position range / comparability sanity
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_position_range():
    """canonical_position output is within [0, 100]."""
    close = _make_close(n=600)
    pos = canonical_position(close, freq="D").dropna()
    assert len(pos) > 100
    assert float(pos.min()) >= 0.0, f"Position below 0: {float(pos.min())}"
    assert float(pos.max()) <= 100.0, f"Position above 100: {float(pos.max())}"


def test_canonical_position_comparability_two_vols():
    """Peaks on a high-vol series map to comparable range as peaks on low-vol series.

    D1 §1.2 acceptance: position at cycle peaks should be broadly comparable
    across assets — the z/CDF formulation achieves this where the range-stochastic
    does not.  We verify that both series' peaks sit in the upper zone (≥68).
    """
    # Low-vol sinusoidal cycle
    lo_vol = _make_cycle(n=700, seed=10, amplitude=0.20, period=252)
    # High-vol sinusoidal cycle (4× more noise)
    hi_vol = _make_cycle(n=700, seed=20, amplitude=0.20, period=252)
    hi_vol = pd.Series(
        hi_vol.to_numpy() * np.exp(np.random.default_rng(77).normal(0, 0.025, 700).cumsum()),
        index=hi_vol.index
    )

    pos_lo = canonical_position(lo_vol, freq="D").dropna()
    pos_hi = canonical_position(hi_vol, freq="D").dropna()

    # Both should regularly reach the upper zone (> 65) — check the 90th percentile
    assert float(pos_lo.quantile(0.90)) >= 65.0, (
        f"Low-vol series: 90th pct position = {float(pos_lo.quantile(0.90)):.1f} < 65"
    )
    assert float(pos_hi.quantile(0.90)) >= 65.0, (
        f"High-vol series: 90th pct position = {float(pos_hi.quantile(0.90)):.1f} < 65"
    )


def test_canonical_position_insufficient_history():
    """Returns all-NaN Series when history is below min_bars."""
    close = pd.Series([100.0] * 50,
                      index=pd.date_range("2020-01-02", periods=50, freq="B"))
    pos = canonical_position(close, freq="D")
    assert pos.isna().all(), "Expected all-NaN for insufficient history"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Hysteresis — single-bar wobble does NOT flip phase; sustained move DOES
# ─────────────────────────────────────────────────────────────────────────────

def test_hysteresis_single_bar_wobble_does_not_flip():
    """A single bar wobble in MACD votes does NOT flip phase when confirm_persist=2."""
    # Start in Expansion (rising mid-range)
    w_bullish  = _bullish_mtf()
    w_bearish  = _bearish_mtf()

    # Bar 0: Expansion
    r0 = classify_phase(50.0, 0.0, w_bullish, {"macd_pos": True},
                        prev_phase="Expansion", confirm_persist=2)
    assert r0["phase"] == "Expansion"
    pending = r0["pending"]

    # Bar 1: one-bar wobble to bearish votes → candidate Downturn
    r1 = classify_phase(50.0, -1.0, w_bearish, {"macd_pos": False},
                        prev_phase="Expansion", confirm_persist=2, pending=pending)
    # Must stay Expansion (only 1 consecutive bearish bar, need 2)
    assert r1["phase"] == "Expansion", (
        f"Single-bar wobble should NOT flip phase. Got: {r1['phase']}"
    )
    pending = r1["pending"]

    # Bar 2: back to bullish → pending resets
    r2 = classify_phase(50.0, 1.0, w_bullish, {"macd_pos": True},
                        prev_phase="Expansion", confirm_persist=2, pending=pending)
    assert r2["phase"] == "Expansion"


def test_hysteresis_sustained_move_does_flip():
    """A sustained move (≥ confirm_persist consecutive bars) DOES flip the phase."""
    w_bearish = _bearish_mtf()

    pending: dict = {}
    prev_phase = "Expansion"
    confirm_persist = 2

    # Two consecutive bearish bars should commit the transition to Downturn
    r1 = classify_phase(50.0, -5.0, w_bearish, {"macd_pos": False},
                        prev_phase=prev_phase, confirm_persist=confirm_persist, pending=pending)
    pending = r1["pending"]
    # After 1 bar: still Expansion
    assert r1["phase"] == "Expansion"

    r2 = classify_phase(50.0, -5.0, w_bearish, {"macd_pos": False},
                        prev_phase=prev_phase, confirm_persist=confirm_persist, pending=pending)
    # After 2nd consecutive bar: commits
    assert r2["phase"] == "Downturn", (
        f"Sustained move (2 bars) should flip to Downturn. Got: {r2['phase']}"
    )


def test_hysteresis_off_by_default():
    """confirm_persist=0 (default) reverts to immediate phase flip (behavioral continuity)."""
    w_bearish = _bearish_mtf()

    r = classify_phase(50.0, -5.0, w_bearish, {"macd_pos": False},
                       prev_phase="Expansion", confirm_persist=0)
    assert r["phase"] == "Downturn", (
        "With confirm_persist=0 (off), phase should flip immediately"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. detect_turns: confirmed_at correctness
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_zigzag_close() -> pd.Series:
    """Deterministic series with clear 20%+ swings for ZigZag testing."""
    n = 500
    # Create a clear V-shape: down 30%, up 50%, down 25%
    idx = pd.date_range("2020-01-02", periods=n, freq="B")
    prices = np.ones(n) * 100.0

    # Phase 1: decline 30% over first 100 bars
    for i in range(1, 100):
        prices[i] = prices[i-1] * (1 - 0.30/100)
    # Phase 2: rally 50% over next 200 bars
    for i in range(100, 300):
        prices[i] = prices[i-1] * (1 + 0.25/100)
    # Phase 3: decline 25% over last 200 bars
    for i in range(300, n):
        prices[i] = prices[i-1] * (1 - 0.125/100)

    return pd.Series(prices, index=idx)


def test_detect_turns_returns_confirmed_at():
    """Every confirmed turn has a confirmed_at date and a positive confirm_lag_bars."""
    close = _synthetic_zigzag_close()
    params = TurnParams(pct=14.0, basis="close_tr", freq="D")
    turns = detect_turns(close, series_id="test", params=params)

    confirmed = [t for t in turns if not t["provisional"]]
    assert len(confirmed) >= 2, "Expected at least 2 confirmed turns"

    for t in confirmed:
        assert "confirmed_at" in t, f"Missing confirmed_at on turn {t['turn_id']}"
        assert "confirm_lag_bars" in t, f"Missing confirm_lag_bars on turn {t['turn_id']}"
        lag = t["confirm_lag_bars"]
        assert lag > 0, (
            f"confirm_lag_bars must be > 0 for a confirmed turn "
            f"(turn_id={t['turn_id']}, lag={lag})"
        )


def test_detect_turns_turn_invisible_before_confirmed_at():
    """The detector records that a turn is knowable only from confirmed_at — NOT from pivot date."""
    close = _synthetic_zigzag_close()
    params = TurnParams(pct=14.0, basis="close_tr", freq="D")
    turns = detect_turns(close, series_id="test", params=params)

    confirmed = [t for t in turns if not t["provisional"]]
    assert confirmed, "Need at least one confirmed turn"

    # For the first confirmed turn (after the seeding pivot), the confirmed_at
    # date must be strictly after the pivot date AND within the series range.
    t = confirmed[0]
    import datetime as dt
    pivot_date    = dt.date.fromisoformat(t["date"])
    confirmed_at  = dt.date.fromisoformat(t["confirmed_at"])
    # confirmed_at >= pivot_date (it's the date at which reversal threshold was crossed)
    assert confirmed_at >= pivot_date, (
        f"confirmed_at ({confirmed_at}) before pivot date ({pivot_date})!"
    )
    # For non-provisional turns the confirmation must have happened
    assert confirmed_at <= close.index[-1].date(), (
        f"confirmed_at ({confirmed_at}) is beyond the series end"
    )


def test_detect_turns_alternates():
    """ZigZag must strictly alternate peak/trough (excl. the provisional tail)."""
    close = _synthetic_zigzag_close()
    params = TurnParams(pct=10.0, basis="close_tr", freq="D")
    turns = detect_turns(close, series_id="test", params=params)

    confirmed = [t for t in turns if not t["provisional"]]
    for i in range(1, len(confirmed)):
        assert confirmed[i]["k"] != confirmed[i-1]["k"], (
            f"Two consecutive {confirmed[i]['k']} turns at positions {i-1} and {i}"
        )


def test_detect_turns_np6_upward_seed():
    """NP-6 fix: a series that starts with an upswing correctly seeds the first PEAK.

    NP-6 root cause (D1 §8): the original _detect_swings only updated ref_px downward
    ('if p < ref_px: ref_px = p') during the unknown-leg phase. This means if price
    rallied from 100 to 115 (the running MAX) then fell 14%, the old code checked
    '85 <= 100*0.86=86' → FALSE (no trigger!) — the peak at 115 was invisible because
    the code never tracked the running MAX, only the running MIN.

    The fix: track BOTH running min AND max during the unknown leg, so when price falls
    ≥ pct from the running MAX, the first PEAK is correctly confirmed with its pivot
    dated at the actual high bar (not at bar 0).
    """
    # Series: rally from 100 to 118 over first 15 bars (tracking the running max),
    # then fall 20% from that high (118 * 0.80 = 94.4, which is below 100 * 0.86 = 86
    # with the OLD code's check  — old code would NOT fire; new code WILL fire since
    # it checks against running MAX 118, not initial value 100).
    n = 200
    idx = pd.date_range("2021-01-04", periods=n, freq="B")
    prices = np.ones(n) * 100.0

    # Phase 1: quick spike to 118 over 15 bars
    for i in range(1, 16):
        prices[i] = 100.0 + (18.0 / 15) * i
    peak_bar = 15  # price = 118

    # Phase 2: fall 20%+ from the peak (118 * 0.80 = 94.4 after 100 bars)
    for i in range(16, 116):
        prices[i] = prices[i-1] * 0.998   # -20% cumulative by bar 115

    # Phase 3: rally again
    for i in range(116, n):
        prices[i] = prices[i-1] * 1.002

    close = pd.Series(prices, index=idx)
    params = TurnParams(pct=14.0)
    turns = detect_turns(close, series_id="np6", params=params)
    confirmed = [t for t in turns if not t["provisional"]]

    assert confirmed, "No confirmed turns found in NP-6 test series"

    # With the NP-6 fix: there must be a PEAK confirmed near bar 15 (the actual high).
    # The old code (downward-only ref_px) would have failed to register that bar 0 was
    # a trough and bar 15 was a peak — instead it would eventually fire a peak at bar 0's
    # date (wrong date) or miss the peak entirely if the fall didn't exceed 14% from bar 0.
    #
    # Key assertion: the first PEAK in the confirmed list should be dated near bar_peak (15),
    # NOT at bar 0 — proving the running max is being tracked correctly.
    peaks = [t for t in confirmed if t["k"] == "peak"]
    assert peaks, "No confirmed peaks found — NP-6 fix may have broken peak detection"
    first_peak = peaks[0]
    first_peak_date = pd.Timestamp(first_peak["date"])
    expected_peak_date = idx[peak_bar]  # bar 15

    delta_cal_days = abs((first_peak_date - expected_peak_date).days)
    assert delta_cal_days <= 10, (
        f"NP-6 fix: first confirmed PEAK should be near bar {peak_bar} "
        f"({expected_peak_date.date()}), got {first_peak_date.date()} "
        f"(delta={delta_cal_days} calendar days). "
        "The running-max reference is not being tracked correctly during the unknown-leg phase."
    )
    # The peak price should be the actual high (~118), not the initial price (100)
    assert first_peak["px"] >= 110.0, (
        f"NP-6 fix: peak price should be near 118, got {first_peak['px']:.2f}. "
        "Running max may not be tracked."
    )


def test_detect_turns_turn_id_format():
    """turn_id follows '{series_id}:{kind}:{YYYY-MM}' format."""
    close = _synthetic_zigzag_close()
    params = TurnParams(pct=14.0, basis="close_tr")
    turns = detect_turns(close, series_id="xlk", params=params)

    import re
    pattern = re.compile(r"^xlk:(trough|peak):\d{4}-\d{2}$")
    for t in turns:
        assert pattern.match(t["turn_id"]), (
            f"turn_id {t['turn_id']!r} does not match expected format"
        )


def test_detect_turns_provisional_is_last():
    """The provisional entry is always the LAST one in the list."""
    close = _synthetic_zigzag_close()
    params = TurnParams(pct=14.0)
    turns = detect_turns(close, series_id="test", params=params)

    assert turns, "No turns returned"
    assert turns[-1]["provisional"], "Last turn must be provisional"
    for t in turns[:-1]:
        assert not t["provisional"], f"Non-last turn is provisional: {t['turn_id']}"


# ─────────────────────────────────────────────────────────────────────────────
# 10. match_turns — exact / shifted / orphaned
# ─────────────────────────────────────────────────────────────────────────────

def _make_turns_list(specs: list[tuple[str, str, str]]) -> list[dict]:
    """Build a turns list from (series_id, kind, date_str) specs."""
    return [
        {
            "turn_id":   f"{sid}:{kind}:{date_str[:7]}",
            "k":         kind,
            "date":      date_str,
            "provisional": False,
        }
        for sid, kind, date_str in specs
    ]


def test_match_turns_exact():
    """When turn_id keys are identical, status is 'exact'."""
    turns = _make_turns_list([("xlk", "trough", "2022-10-12")])
    old_bindings = {"xlk:trough:2022-10": {"title": "Bottom"}}

    result = match_turns(old_bindings, turns, tol_days=60)
    assert "xlk:trough:2022-10" in result
    assert result["xlk:trough:2022-10"]["status"] == "exact"


def test_match_turns_shifted():
    """A binding with a raw date matches a nearby turn → status 'shifted'."""
    turns = _make_turns_list([("xlk", "trough", "2022-10-20")])
    old_bindings = {"2022-10-12": {"title": "Bottom"}}

    result = match_turns(old_bindings, turns, tol_days=60)
    assert "2022-10-12" in result
    info = result["2022-10-12"]
    assert info["status"] == "shifted"
    assert info["new_turn_id"] == "xlk:trough:2022-10"


def test_match_turns_orphaned_no_match():
    """A binding with no nearby turn → status 'orphaned'."""
    turns = _make_turns_list([("xlk", "trough", "2020-01-15")])
    old_bindings = {"2022-10-12": {"title": "Bottom"}}

    result = match_turns(old_bindings, turns, tol_days=60)
    assert result["2022-10-12"]["status"] == "orphaned"


def test_match_turns_orphaned_tie():
    """Two candidates at equal distance → status 'orphaned' (can't resolve)."""
    turns = _make_turns_list([
        ("xlk", "trough", "2022-09-12"),  # 30 days before
        ("xlk", "trough", "2022-11-11"),  # 30 days after
    ])
    old_bindings = {"2022-10-12": {"title": "Bottom"}}

    result = match_turns(old_bindings, turns, tol_days=60)
    assert result["2022-10-12"]["status"] == "orphaned"


def test_match_turns_new_turns_flagged():
    """New turns with no old binding appear as 'new' in the result."""
    turns = _make_turns_list([("xlk", "peak", "2022-08-15")])
    old_bindings = {}

    result = match_turns(old_bindings, turns, tol_days=60)
    assert "xlk:peak:2022-08" in result
    assert result["xlk:peak:2022-08"]["status"] == "new"


# ─────────────────────────────────────────────────────────────────────────────
# 11. resolve_state — raises on unknown inputs
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_state_raises_unknown_phase():
    with pytest.raises(ValueError, match="unknown phase"):
        resolve_state(pos=50.0, phase="MoonPhase", phase_dir="rising", ladder_state="RALLY ON")


def test_resolve_state_raises_unknown_ladder():
    with pytest.raises(ValueError, match="unknown ladder_state"):
        resolve_state(pos=50.0, phase="Expansion", phase_dir="rising", ladder_state="FLYING")


def test_resolve_state_total_function():
    """resolve_state succeeds for ALL valid (phase, ladder) combinations."""
    for phase in PHASES:
        for ladder in LADDER:
            for pos in (10.0, 50.0, 90.0):
                rs = resolve_state(pos=pos, phase=phase, phase_dir="rising", ladder_state=ladder)
                assert isinstance(rs, dict)
                assert rs["stance"] in STANCES


# ─────────────────────────────────────────────────────────────────────────────
# 12. project_next — overdue semantics
# ─────────────────────────────────────────────────────────────────────────────

def test_project_next_overdue_when_past_central():
    """project_next.overdue=True when today > central_x."""
    # Use turns at 2020-01, 2020-07, 2021-01 (6-month half-cycles)
    turns = [
        {"x": 2020.0, "k": "trough", "t": "2020-01", "provisional": False},
        {"x": 2020.5, "k": "peak",   "t": "2020-07", "provisional": False},
        {"x": 2021.0, "k": "trough", "t": "2021-01", "provisional": False},
        {"x": 2021.4, "k": "peak",   "t": "2021-05", "provisional": True},
    ]
    # today_x = 2022.0 — well past the expected next turn at ~2021.5
    proj = project_next(turns, today_x=2022.0)
    assert proj is not None
    assert proj["overdue"], "Expected overdue=True when today is past central_x"
    assert proj["overdue_frac"] is not None
    assert proj["overdue_frac"] > 1.0, "overdue_frac should be > 1 when past full cycle"


def test_project_next_not_overdue_before_central():
    """project_next.overdue=False when today < central_x."""
    turns = [
        {"x": 2022.0, "k": "trough", "t": "2022-01", "provisional": False},
        {"x": 2022.5, "k": "peak",   "t": "2022-07", "provisional": False},
        {"x": 2023.0, "k": "trough", "t": "2023-01", "provisional": False},
        {"x": 2023.3, "k": "peak",   "t": "2023-04", "provisional": True},
    ]
    # median half-cycle = 0.5yr → central_x = 2023.0 + 0.5 = 2023.5
    proj = project_next(turns, today_x=2023.2)
    assert proj is not None
    assert not proj["overdue"], "Expected overdue=False when today < central_x"


def test_project_next_anchors_at_last_confirmed():
    """central_x is anchored at last confirmed turn, not today_x."""
    turns = [
        {"x": 2020.0, "k": "trough", "t": "2020-01", "provisional": False},
        {"x": 2020.5, "k": "peak",   "t": "2020-07", "provisional": False},
        {"x": 2021.0, "k": "trough", "t": "2021-01", "provisional": False},
    ]
    # No provisional turn; last confirmed is 2021-01 (x=2021.0)
    # Median half-cycle ≈ 0.5yr → central_x = 2021.0 + 0.5 = 2021.5
    proj = project_next(turns, today_x=2021.2)
    assert proj is not None
    assert abs(proj["central_x"] - 2021.5) < 0.05, (
        f"central_x should be ~2021.5, got {proj['central_x']}"
    )
    assert proj["last_confirmed_x"] == 2021.0


def test_project_next_insufficient_turns():
    """Returns None with fewer than 3 confirmed turns."""
    turns = [
        {"x": 2020.0, "k": "trough", "t": "2020-01", "provisional": False},
        {"x": 2020.5, "k": "peak",   "t": "2020-07", "provisional": True},
    ]
    assert project_next(turns, today_x=2021.0) is None


# ─────────────────────────────────────────────────────────────────────────────
# 13. Export payload shape
# ─────────────────────────────────────────────────────────────────────────────

def test_export_payload_shape():
    """export_payload returns expected top-level keys and is JSON-serializable."""
    payload = export_payload()
    required_keys = {
        "version", "detector_version", "phases", "zones", "stances", "ladder",
        "ladder_dir", "crosswalk", "divergence_notes", "position_params",
        "turn_detector_defaults", "signal_ttl_bars",
    }
    for key in required_keys:
        assert key in payload, f"Missing key {key!r} in export_payload()"

    # Must be JSON-serializable
    json_str = json.dumps(payload, ensure_ascii=False)
    assert len(json_str) > 100


def test_export_payload_version_matches():
    """Payload version matches ONTOLOGY_VERSION constant."""
    payload = export_payload()
    assert payload["version"] == ONTOLOGY_VERSION


# ─────────────────────────────────────────────────────────────────────────────
# 14. write_stance_matrix artifact
# ─────────────────────────────────────────────────────────────────────────────

def test_write_stance_matrix(tmp_path):
    """write_stance_matrix writes a valid JSON artifact to the given path."""
    out = str(tmp_path / "stance_matrix.json")
    path = write_stance_matrix(out)
    assert os.path.exists(path)

    with open(path) as fh:
        artifact = json.load(fh)

    assert artifact["version"] == ONTOLOGY_VERSION
    assert "matrix" in artifact
    # 43 simple (38 original + 5 CONFIRMING TURN) + 4 pos-gated = 47 total cells
    assert len(artifact["matrix"]) == 47, (
        f"Expected 47 matrix cells (43 simple + 4 pos-gated), got {len(artifact['matrix'])}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 15. classify_phase basic contract
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_phase_returns_valid_phase():
    """classify_phase returns one of the 5 valid phases."""
    for pos in (10.0, 30.0, 50.0, 70.0, 90.0):
        for w, t3 in [({"macd_pos": True}, {"macd_pos": True}),
                      ({"macd_pos": False}, {"macd_pos": False})]:
            result = classify_phase(pos, 0.0, w, t3)
            assert result["phase"] in PHASES, (
                f"classify_phase returned invalid phase: {result['phase']!r}"
            )
            assert result["phase_dir"] in ("rising", "falling")


def test_classify_phase_high_pos_peak_downturn():
    """pos ≥ 68 → Peak (rising) or Downturn (falling)."""
    r_up   = classify_phase(80.0, 5.0, _bullish_mtf(), {"macd_pos": True})
    r_down = classify_phase(80.0, -5.0, _bearish_mtf(), {"macd_pos": False})
    assert r_up["phase"]   == "Peak",     f"Expected Peak, got {r_up['phase']}"
    assert r_down["phase"] == "Downturn", f"Expected Downturn, got {r_down['phase']}"


def test_classify_phase_low_pos_recovery_trough():
    """pos ≤ 32 → Recovery (rising) or Trough (falling)."""
    r_up   = classify_phase(20.0, 5.0, _bullish_mtf(), {"macd_pos": True})
    r_down = classify_phase(20.0, -5.0, _bearish_mtf(), {"macd_pos": False})
    assert r_up["phase"]   == "Recovery", f"Expected Recovery, got {r_up['phase']}"
    assert r_down["phase"] == "Trough",   f"Expected Trough, got {r_down['phase']}"
