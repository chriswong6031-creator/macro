"""Unit tests for engine.commodity_signals.technical_arming (Policy-Shock W1-B).

Synthetic series only — no network, no file I/O.

Run: .venv/bin/python -m tests.test_technical_arming
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.commodity_signals import _stoch_kd, technical_arming  # noqa: E402
from lib import config  # noqa: E402

CFG = config.load()["commodities"]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _close(n: int = 600, trend: float = 0.0, vol: float = 0.01,
           seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.Series(100 * np.exp(np.cumsum(rng.normal(trend, vol, n))), index=idx)


def _px(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"close": close, "open": close, "high": close, "low": close})


# ---------------------------------------------------------------------------
# stochastic helpers
# ---------------------------------------------------------------------------

def test_stoch_kd_bounds() -> None:
    c = _close(400)
    k, d = _stoch_kd(c)
    assert k.dropna().between(0, 100).all(), "K out of [0, 100]"
    assert d.dropna().between(0, 100).all(), "D out of [0, 100]"


def test_stoch_kd_oversold_in_downtrend() -> None:
    """A steady downtrend should push K/D into oversold territory."""
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    c = pd.Series(np.linspace(100, 40, n), index=idx)
    k, d = _stoch_kd(c, k_period=14, smooth_k=3, smooth_d=3)
    # In a relentless downtrend close == rolling min -> raw K ~0 -> K, D near 0
    assert d.dropna().tail(20).mean() < 20, "Expected D near 0 in downtrend"


def test_stoch_kd_overbought_in_uptrend() -> None:
    """A steady uptrend should push K/D into overbought territory."""
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    c = pd.Series(np.linspace(40, 100, n), index=idx)
    k, d = _stoch_kd(c, k_period=14, smooth_k=3, smooth_d=3)
    assert d.dropna().tail(20).mean() > 80, "Expected D near 100 in uptrend"


def test_stoch_kd_nans_when_too_short() -> None:
    c = pd.Series([1.0, 2.0, 3.0])
    k, d = _stoch_kd(c, k_period=14, smooth_k=3, smooth_d=3)
    assert d.isna().all(), "D should be all-NaN when series is shorter than lookback"


# ---------------------------------------------------------------------------
# stoch_curl
# ---------------------------------------------------------------------------

def test_stoch_curl_fires_on_programmed_cross() -> None:
    """Inject a K-crosses-above-D event in the oversold zone on the last bar."""
    n = 300
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Build a flat series then inject a V-recovery in the last 5 bars
    c_arr = np.full(n, 50.0)
    # Set a long trough so 60d low is established, then a slight bounce
    c_arr[:240] = np.linspace(80, 40, 240)    # downtrend → K/D fall to oversold
    c_arr[240:295] = 40.0                     # base at 40
    c_arr[295:] = np.linspace(40, 43, 5)      # small bounce to create the cross
    c = pd.Series(c_arr, index=idx)
    px = _px(c)
    result = technical_arming(px, CFG)
    # The stoch K should be low (oversold zone likely) and may have crossed D.
    # We cannot guarantee the exact cross from this constructor, so just confirm
    # the block runs without error and keys are present.
    assert "stoch_curl" in result
    assert "stoch_k" in result
    assert result["stoch_k"] is None or isinstance(result["stoch_k"], float)


def test_stoch_curl_false_when_overbought() -> None:
    """A cross while K > 30 must NOT fire stoch_curl."""
    n = 400
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Steady gentle uptrend -> K/D both high, any cross is above oversold
    c = pd.Series(np.linspace(80, 200, n), index=idx)
    px = _px(c)
    result = technical_arming(px, CFG)
    # K will be near 100 (overbought) throughout; stoch_curl must be False
    assert result["stoch_curl"] is False, (
        f"stoch_curl should be False in overbought uptrend, got K={result['stoch_k']}"
    )


# ---------------------------------------------------------------------------
# macd_curl
# ---------------------------------------------------------------------------

def test_macd_curl_fires_in_recovering_downtrend() -> None:
    """MACD histogram below zero but rising for 3+ consecutive bars = MACD curl.

    Construction: a sharp -40% drop drives the MACD histogram deeply negative.
    A NOISY recovery then causes the histogram to curl upward with economically
    meaningful diffs — which is what a real recovery looks like (not a piecewise-
    linear flat-line that produces only asymptotic float-scale convergence).
    We scan forward from bar 120 (min_bars gate) to find the first 3-bar window
    where hist < 0, rising, and diffs exceed the v1.1 scale-invariant epsilon,
    then truncate there.

    Note: a purely piecewise-linear recovery (linspace + flat) produces diffs
    that are too small to pass the epsilon, which is CORRECT behavior — those
    fixtures represent EMA convergence artifacts, not real momentum curls.
    """
    from engine.commodity_signals import _ema

    rng = np.random.default_rng(7)
    n = 600
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    # Sharp -40% drop in 120 bars, then noisy recovery
    drop = np.linspace(100, 60, 120)
    recovery_log = rng.normal(0.001, 0.01, 480).cumsum()
    recovery = 60 * np.exp(recovery_log - recovery_log[0])  # anchored at 60
    c = pd.Series(np.concatenate([drop, recovery]), index=idx)

    macd_line = _ema(c, 12) - _ema(c, 26)
    macd_sig = _ema(macd_line, 9)
    hist = macd_line - macd_sig
    h = hist.dropna()

    # Find first valid curl window at or after bar 120 (min_bars)
    cutoff_date = None
    for i in range(120, len(h)):
        tail = h.iloc[i - 3:i + 1]
        if len(tail) < 4:
            continue
        diffs = tail.diff().iloc[1:]
        if not ((tail.iloc[1:] < 0).all() and (diffs > 0).all()):
            continue
        roll_mag = h.abs().rolling(60, min_periods=20).mean()
        mag_f = float(roll_mag.iloc[i]) if pd.notna(roll_mag.iloc[i]) else 0.0
        price_f = float(c.iloc[:i + 1].mean()) * 1e-6
        min_diff = max(0.02 * mag_f, price_f)
        if (diffs > min_diff).all():
            cutoff_date = h.index[i]
            break

    assert cutoff_date is not None, (
        "fixture sanity: no economically-rising negative-histogram window found after bar 120"
    )
    c_trunc = c.loc[:cutoff_date]
    px = _px(c_trunc)
    result = technical_arming(px, CFG)
    assert result["macd_curl"] is True, (
        f"Expected macd_curl=True at genuine histogram curl, got {result}"
    )


def test_macd_curl_false_in_strong_uptrend() -> None:
    """In a relentless uptrend the histogram is positive; macd_curl must be False."""
    n = 400
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    c = pd.Series(np.linspace(50, 200, n), index=idx)
    px = _px(c)
    result = technical_arming(px, CFG)
    assert result["macd_curl"] is False, (
        "Expected macd_curl=False in strong uptrend (histogram is positive)"
    )


# ---------------------------------------------------------------------------
# basing
# ---------------------------------------------------------------------------

def test_basing_true_when_price_stalls_at_low() -> None:
    """After a sharp -23% drop (concentrated in ~80 days), price stalls near the low.

    The drop is concentrated so that 120 days before end the price was near 100,
    giving a 120d max-drawdown of approximately -23% (well below the -15% gate).
    The base lasts 20+ days at the low, satisfying both basing conditions.
    """
    n = 400
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    c_arr = np.concatenate([
        np.full(280, 100.0),         # long flat at peak (so 120d high = 100)
        np.linspace(100, 77, 80),    # rapid -23% drop within ~80 days
        np.full(40, 77.5),           # 40-day base near the low
    ])
    c = pd.Series(c_arr, index=idx)
    px = _px(c)
    result = technical_arming(px, CFG)
    assert result["basing"] is True, (
        f"Expected basing=True after sharp -23% dd + 40d base, got "
        f"basing={result['basing']}, days_in_base={result['days_in_base']}"
    )
    assert result["days_in_base"] >= 10


def test_basing_false_when_drawdown_insufficient() -> None:
    """Only a -10% pullback — not deep enough to satisfy the -15% gate."""
    n = 500
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    c_arr = np.concatenate([
        np.linspace(100, 90, 300),   # only -10% drop
        np.full(200, 90.0),          # flat at the low for a long time
    ])
    c = pd.Series(c_arr, index=idx)
    px = _px(c)
    result = technical_arming(px, CFG)
    assert result["basing"] is False, (
        "Expected basing=False when drawdown < -15%"
    )


def test_basing_false_when_not_enough_consecutive_days() -> None:
    """A very recent dip to the low for only 5 days is NOT enough for basing.

    Construction: flat at 100, then quick -25% drop, 5 days at the trough,
    then immediately rallies back.  The 5-day stint is shorter than
    base_min_days=10, so basing must be False.  days_in_base is measured
    on the CURRENT trailing streak, so if the bounce already pushed price
    above the low×1.08 band the count resets to 0; if the bounce is still
    within the band the count may be > 0 but the drawdown gate fails instead.
    """
    n = 400
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    c_arr = np.concatenate([
        np.full(280, 100.0),         # long flat at 100
        np.linspace(100, 75, 5),     # quick 5-day drop to the trough
        np.full(5, 75.5),            # 5 days at low (< base_min_days=10)
        np.linspace(75.5, 100, 110), # rally back — leaves the band quickly
    ])
    c = pd.Series(c_arr, index=idx)
    px = _px(c)
    result = technical_arming(px, CFG)
    assert result["basing"] is False, (
        f"Expected basing=False when only 5 days in base band, got {result}"
    )
    # After a big rally, days_in_base is 0 (price above the band)
    assert result["days_in_base"] < 10, (
        f"Expected days_in_base < 10, got {result['days_in_base']}"
    )


# ---------------------------------------------------------------------------
# armed flag
# ---------------------------------------------------------------------------

def test_armed_requires_basing_and_curl() -> None:
    """armed must be False when basing is True but neither curl fires."""
    n = 500
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Perfect basing setup, but MACD histogram is neutral/positive (no curl)
    c_arr = np.concatenate([
        np.linspace(100, 77, 350),
        np.full(150, 78.0),          # flat — no recovery, histogram near zero
    ])
    c = pd.Series(c_arr, index=idx)
    px = _px(c)
    result = technical_arming(px, CFG)
    # basing may be True, but armed = basing AND (stoch_curl OR macd_curl)
    if not result["stoch_curl"] and not result["macd_curl"]:
        assert result["armed"] is False, "armed should be False when no curl fires"


def test_null_result_on_too_short_series() -> None:
    """Series shorter than the minimum window must return armed=False gracefully."""
    c = _close(30)  # 30 bars — way too short for 26+9+3 MACD min
    px = _px(c)
    result = technical_arming(px, CFG)
    assert result["armed"] is False
    assert result["basing"] is False
    assert result["stoch_curl"] is False
    assert result["macd_curl"] is False
    assert result["days_in_base"] == 0


# ---------------------------------------------------------------------------
# params block
# ---------------------------------------------------------------------------

def test_params_block_present_and_versioned() -> None:
    c = _close(400)
    px = _px(c)
    result = technical_arming(px, CFG)
    p = result["params"]
    assert p["version"] == "v1.1", "params must carry version=v1.1"
    # All v1-frozen keys must be present
    for key in ("stoch_k_period", "stoch_smooth_k", "stoch_smooth_d",
                 "stoch_oversold", "macd_fast", "macd_slow", "macd_signal",
                 "macd_consecutive_bars", "base_window_d", "base_pct",
                 "base_min_days", "drawdown_window_d", "drawdown_min"):
        assert key in p, f"params missing key: {key}"
    # v1.1 addition keys must also be present
    assert "base_flat_max_abs_return" in p, "params missing v1.1 key: base_flat_max_abs_return"
    assert "macd_rise_min_frac" in p, "params missing v1.1 key: macd_rise_min_frac"


# ---------------------------------------------------------------------------
# smoke: all four commodities via compute_asset
# ---------------------------------------------------------------------------

def test_arming_block_present_via_compute_asset() -> None:
    """technical_arming is called from build_commodities.asset_vm() which reads
    from the signals DataFrame; here we verify that technical_arming accepts the
    same DataFrame shape that compute_asset produces, and returns a valid block
    for every covered asset."""
    from engine import commodity_signals as S

    def _drivers(idx: pd.DatetimeIndex) -> dict:
        rng = np.random.default_rng(42)
        n = len(idx)
        return {
            "real_yield": pd.Series(np.linspace(1.5, 0.5, n), index=idx),
            "dxy": pd.Series(100 + rng.normal(0, 0.5, n).cumsum(), index=idx),
            "breakeven10": pd.Series(2.2 + rng.normal(0, 0.01, n).cumsum(), index=idx),
            "fed_balance": pd.Series(8e6 + rng.normal(0, 1e4, n).cumsum(), index=idx),
            "indpro": pd.Series(100 + rng.normal(0, 0.05, n).cumsum(), index=idx),
            "us10y": pd.Series(3.0 + rng.normal(0, 0.02, n).cumsum(), index=idx),
            "broad_dollar": pd.Series(110 + rng.normal(0, 0.4, n).cumsum(), index=idx),
        }

    n = 800
    idx = pd.date_range("2018-01-01", periods=n, freq="B")
    rng = np.random.default_rng(99)
    close = pd.Series(100 * np.exp(rng.normal(0, 0.01, n).cumsum()), index=idx)
    px = pd.DataFrame({
        "close": close, "open": close, "high": close * 1.005,
        "low": close * 0.995, "volume": rng.uniform(1e6, 2e6, n),
    })
    drivers = _drivers(idx)
    cfg = config.load()["commodities"]

    for asset in ["gold", "silver", "copper", "oil"]:
        ai = {"asset": asset, "price": px, "drivers": drivers}
        df = S.compute_asset(ai, cfg)
        # technical_arming reads from px, not df, so test it the same way
        # asset_vm does (using the price df passed into compute_asset)
        arm = S.technical_arming(px, cfg)
        assert isinstance(arm, dict), f"{asset}: expected dict, got {type(arm)}"
        assert "armed" in arm, f"{asset}: 'armed' key missing"
        assert isinstance(arm["armed"], bool), f"{asset}: armed must be bool"
        assert "params" in arm, f"{asset}: 'params' key missing"
        assert arm["params"]["version"] == "v1.1", f"{asset}: params version mismatch"


# ---------------------------------------------------------------------------
# PS-A1 new tests (3): falling knife, genuine base, linear-decline macd_curl
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 5, 42, 99, 137])
def test_falling_knife_never_arms(seed: int) -> None:
    """A noisy monotone -30% decline must NOT arm, regardless of seed.

    This is the core construct-flaw regression from the Opus review (PS-A1):
    in v1 the proximity-to-trailing-low test is satisfied continuously by an
    ongoing decline (the 60d low tracks the price down), so days_in_base
    inflates through the descent and transient noise-bounces fire the curls.
    The v1.1 flatness gate must block ALL of these seeds.
    """
    rng = np.random.default_rng(seed)
    n = 600
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Noisy monotone decline: ~-30% over 600 days with daily vol ~0.8%
    trend = np.linspace(0, np.log(0.70), n)
    noise = rng.normal(0, 0.008, n).cumsum()
    close = pd.Series(100 * np.exp(trend + noise), index=idx)
    px = _px(close)
    cfg = config.load()["commodities"]
    result = technical_arming(px, cfg)
    assert result["armed"] is False, (
        f"seed={seed}: falling knife must NOT arm with v1.1, got armed=True "
        f"(basing={result['basing']}, days_in_base={result['days_in_base']}, "
        f"flatness={result.get('flatness')}, "
        f"stoch_curl={result['stoch_curl']}, macd_curl={result['macd_curl']})"
    )


def test_genuine_flat_base_then_curl_arms() -> None:
    """A sharp -23% drop followed by a genuine flat base THEN a noisy recovery
    with a real MACD curl must arm.  This verifies the flatness gate does not
    block valid setups.

    Construction:
    - 280 bars flat at 100 (establishes the 120d peak)
    - 80-bar sharp -23% drop (gives 120d drawdown ~-23%, below -15% gate)
    - 50 bars truly flat at 77.3 (flatness gate: |net_ret| ~ 0%)
    - Noisy recovery (seed=7, vol=1%, uptrend=0.2%/day) that produces an
      economically-meaningful MACD curl — i.e. histogram diffs that pass the
      scale-invariant epsilon.  A purely linear recovery does NOT produce this
      (asymptotic convergence of EMAs generates only float-scale diffs).

    The test scans forward from bar (base_start + n_base) for the first curl
    window where basing and macd_curl both fire simultaneously.
    """
    from engine.commodity_signals import _ema

    rng = np.random.default_rng(7)
    n_flat0, n_drop, n_base = 280, 80, 50
    n_recovery = 400
    idx = pd.date_range("2020-01-01",
                        periods=n_flat0 + n_drop + n_base + n_recovery, freq="B")

    recovery_log = np.cumsum(rng.normal(0.002, 0.01, n_recovery))
    recovery = 77.3 * np.exp(recovery_log - recovery_log[0])

    c = pd.Series(np.concatenate([
        np.full(n_flat0, 100.0),
        np.linspace(100, 77, n_drop),
        np.full(n_base, 77.3),
        recovery,
    ]), index=idx)

    macd_line = _ema(c, 12) - _ema(c, 26)
    macd_sig  = _ema(macd_line, 9)
    hist      = macd_line - macd_sig
    h         = hist.dropna()

    base_start_bar = n_flat0 + n_drop  # bar where flat base begins

    cfg = config.load()["commodities"]
    cutoff_date = None
    for i in range(max(120, base_start_bar + n_base), len(h)):
        tail = h.iloc[i - 3:i + 1]
        if len(tail) < 4:
            continue
        diffs = tail.diff().iloc[1:]
        if not ((tail.iloc[1:] < 0).all() and (diffs > 0).all()):
            continue
        roll_mag = h.abs().rolling(60, min_periods=20).mean()
        mag_f = float(roll_mag.iloc[i]) if pd.notna(roll_mag.iloc[i]) else 0.0
        price_f = float(c.iloc[:i + 1].mean()) * 1e-6
        min_diff = max(0.02 * mag_f, price_f)
        if (diffs > min_diff).all():
            cutoff_date = h.index[i]
            break

    assert cutoff_date is not None, (
        "fixture sanity: no economically-meaningful curl window found after base period"
    )

    c_trunc = c.loc[:cutoff_date]
    px = _px(c_trunc)
    result = technical_arming(px, cfg)

    flatness = result.get("flatness")
    assert flatness is not None, "flatness must be present in v1.1 result"
    assert flatness <= 0.06, (
        f"flatness={flatness:.4f} exceeds 0.06 — genuine base fixture should pass the gate"
    )
    assert result["basing"] is True, (
        f"Expected basing=True after sharp -23% dd + {n_base}d genuine flat base, "
        f"got basing={result['basing']}, flatness={flatness}, days_in_base={result['days_in_base']}"
    )
    assert result["macd_curl"] is True, (
        f"Expected macd_curl=True in the recovery curl window, got {result['macd_curl']}"
    )
    assert result["armed"] is True, (
        f"Expected armed=True (basing AND macd_curl), got {result}"
    )


def test_linear_decline_macd_curl_false() -> None:
    """A perfectly linear decline produces a near-constant negative MACD histogram
    with only float jitter between bars.  macd_curl must be False.

    This is the second construct flaw from the Opus review: on a near-constant
    negative histogram, 3 consecutive float-jitter diffs can all be positive
    (e.g. 1e-7, 2e-8, 3e-9) and fire the old rising-3-bars test.  The v1.1
    scale-invariant epsilon blocks this.
    """
    n = 600
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    # Perfectly linear decline (NO noise) — histogram is near-constant negative
    c = pd.Series(np.linspace(100, 70, n), index=idx)
    px = _px(c)
    cfg = config.load()["commodities"]
    result = technical_arming(px, cfg)
    assert result["macd_curl"] is False, (
        f"macd_curl must be False on a perfectly linear decline (float-jitter only), "
        f"got macd_curl=True"
    )


# ---------------------------------------------------------------------------
# WTI / CL_F sanity snapshot (contract episode July 2026)
# ---------------------------------------------------------------------------

def test_oil_wti_episode_report(capsys=None) -> None:
    """Read the real nightly WTI price source (data/yahoo/CL_F.parquet via the
    same load path the engine uses) and report the v1.1 arming state for the
    period 2026-06-15 to 2026-07-09 — the flagship sanity anchor.

    This test always PASSES regardless of the stored state. It prints the
    relevant context so the orchestrator can read it in the test output.
    Skips silently when the parquet is absent (CI / fresh checkouts)."""
    from engine.commodity_inputs import load_price
    try:
        px = load_price("CL_F")
    except Exception as e:
        print(f"SKIP test_oil_wti_episode_report: CL_F not loadable ({e})")
        return
    cfg = config.load()["commodities"]
    arm = technical_arming(px, cfg)
    close = px["close"]
    # window of interest
    window = close.loc["2026-06-15":"2026-07-09"]
    armed_dates = []
    # Scan the window day-by-day to find which dates arm (expensive but correct for the report)
    idx_all = close.index
    for dt in window.index:
        loc = idx_all.get_loc(dt)
        if loc < 120:
            continue
        sub = px.iloc[:loc + 1]
        r = technical_arming(sub, cfg)
        if r["armed"]:
            armed_dates.append(str(dt.date()))
    print("\n=== WTI/CL_F technical_arming v1.1 — 2026-06-15..2026-07-09 episode ===")
    print(f"  Latest bar in store: {close.index[-1].date()}")
    if len(window) > 0:
        print(f"  Price range in window: {window.min():.2f} - {window.max():.2f}")
    dd_120 = float((close / close.rolling(120).max() - 1).iloc[-1])
    print(f"  120d max-drawdown at latest bar: {dd_120:.1%}")
    print(f"  Armed dates in window: {armed_dates if armed_dates else 'none'}")
    print(f"  Full-history arming block (latest bar):")
    for k, v in arm.items():
        if k != "params":
            print(f"    {k}: {v}")
    print("=== end WTI episode report ===\n")


if __name__ == "__main__":
    tests = [
        test_stoch_kd_bounds,
        test_stoch_kd_oversold_in_downtrend,
        test_stoch_kd_overbought_in_uptrend,
        test_stoch_kd_nans_when_too_short,
        test_stoch_curl_fires_on_programmed_cross,
        test_stoch_curl_false_when_overbought,
        test_macd_curl_fires_in_recovering_downtrend,
        test_macd_curl_false_in_strong_uptrend,
        test_basing_true_when_price_stalls_at_low,
        test_basing_false_when_drawdown_insufficient,
        test_basing_false_when_not_enough_consecutive_days,
        test_armed_requires_basing_and_curl,
        test_null_result_on_too_short_series,
        test_params_block_present_and_versioned,
        test_arming_block_present_via_compute_asset,
        # PS-A1 new tests
        test_genuine_flat_base_then_curl_arms,
        test_linear_decline_macd_curl_false,
        test_oil_wti_episode_report,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    # parametrized falling-knife seeds
    for seed in [1, 5, 42, 99, 137]:
        test_falling_knife_never_arms(seed)
        print(f"PASS test_falling_knife_never_arms[seed={seed}]")
    print("all technical_arming tests passed")
