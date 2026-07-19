"""scripts/build_tech_parity_fixtures.py — Generate deterministic parity fixtures.

Generates a DETERMINISTIC synthetic OHLCV series (numpy default_rng(42), ~500
business-day bars) and computes per-bar indicator LINE values using the canonical
engine modules. The output JSON fixtures are committed to
tests/fixtures/tech_parity/ and serve as the anti-drift contract between this
repo's engine and the Terminal's TypeScript indicatorMath (TLT-R5).

Fixtures written
----------------
  tests/fixtures/tech_parity/ohlcv.json
      The synthetic OHLCV input series.

  tests/fixtures/tech_parity/expected_ichimoku.json
      Per-bar Ichimoku line values: tenkan, kijun, span_a, span_b, chikou.
      null during warmup per the engine's NaN handling.

  tests/fixtures/tech_parity/expected_ribbon.json
      Per-bar ribbon EMA values: fast_ema (span=20), slow_ema (span=50),
      ribbon_state (+1/0/-1).

  tests/fixtures/tech_parity/expected_rsi.json
      Per-bar RSI values: rsi_7, rsi_14, rsi_21 (Wilder/SMA-seeded RMA,
      the canonical engine.canon.rsi).

  tests/fixtures/tech_parity/expected_bollinger.json
      Per-bar Bollinger Band values: upper, mid, lower (SMA(20), 2*std).

  tests/fixtures/tech_parity/expected_m2.json
      Per-bar Indicators M2 values (daily-bar approximations over typical price):
        rolling_vwap_n20      — rolling VWAP (n=20), null during warmup
        week_anchored_vwap    — week-anchored VWAP (resets each W-FRI period)
        anchored_vwap_pos50   — anchored VWAP from positional index 50 inclusive
        rolling_poc_w126_b24  — rolling POC (window=126, bins=24), null during warmup
        volume_profile_final  — volume_profile dict for the final bar (full 500-bar window)

Tolerance contract
------------------
See tests/fixtures/tech_parity/README.md — 1e-6 relative tolerance.

USAGE
-----
    python scripts/build_tech_parity_fixtures.py [--output-dir PATH]

    --output-dir   write fixtures here (default: tests/fixtures/tech_parity)

Run to regenerate: python scripts/build_tech_parity_fixtures.py
Regeneration must produce byte-identical output (determinism guard, TLT-R5).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import os
os.chdir(_REPO_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
log = logging.getLogger("build_tech_parity_fixtures")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "tests" / "fixtures" / "tech_parity"
_N_BARS = 500       # ~500 business-day bars (~2 years of trading data)
_RNG_SEED = 42      # determinism: must never change


# ---------------------------------------------------------------------------
# Synthetic OHLCV generator
# ---------------------------------------------------------------------------

def _generate_ohlcv(n: int = _N_BARS, seed: int = _RNG_SEED) -> pd.DataFrame:
    """Generate deterministic synthetic OHLCV.

    Uses numpy.random.default_rng(seed) for full reproducibility.
    Returns a DataFrame with DatetimeIndex on business days, columns:
    open, high, low, close, volume.
    """
    rng = np.random.default_rng(seed)

    # Geometric random walk for close (realistic vol ~1.2% daily)
    log_rets = rng.normal(0.0002, 0.012, size=n)
    close = 100.0 * np.exp(np.cumsum(log_rets))

    # High/low: add intrabar noise
    high_noise = rng.uniform(0.001, 0.025, size=n)
    low_noise = rng.uniform(0.001, 0.025, size=n)
    high = close * (1.0 + high_noise)
    low = close * (1.0 - low_noise)
    # Ensure open is consistent
    open_ = np.roll(close, 1)
    open_[0] = close[0] * (1.0 + rng.normal(0, 0.005))

    # Volume: log-normal around 5M shares
    volume = rng.lognormal(mean=15.5, sigma=0.4, size=n)

    dates = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame(
        {
            "open": np.round(open_, 6),
            "high": np.round(high, 6),
            "low": np.round(low, 6),
            "close": np.round(close, 6),
            "volume": np.round(volume, 0),
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# None/NaN serializer
# ---------------------------------------------------------------------------

def _to_nullable(v: Any) -> float | None:
    """Convert numpy NaN or pd.NA to None for JSON serialization."""
    if v is None:
        return None
    try:
        if np.isnan(v):
            return None
    except (TypeError, ValueError):
        pass
    return float(v)


def _series_to_list(s: pd.Series) -> list[float | None]:
    """Convert a Series to a list with NaN→None for JSON."""
    return [_to_nullable(v) for v in s.values]


# ---------------------------------------------------------------------------
# Ichimoku line computation
# ---------------------------------------------------------------------------

def _compute_ichimoku(df: pd.DataFrame) -> dict[str, list[float | None]]:
    """Compute Ichimoku line-level values using engine.ichimoku_signals._ichimoku_components.

    Returns dict of per-bar arrays: tenkan, kijun, span_a, span_b, chikou.
    Null (None) during warmup per the engine's NaN handling.
    """
    from engine.ichimoku_signals import (  # noqa: PLC0415
        _ichimoku_components,
        DEFAULT_TENKAN, DEFAULT_KIJUN, DEFAULT_SENKOU_B, DEFAULT_DISPLACEMENT,
    )

    close, tenkan, kijun, cloud_top, cloud_bot = _ichimoku_components(
        df,
        tenkan=DEFAULT_TENKAN,
        kijun=DEFAULT_KIJUN,
        senkou_b=DEFAULT_SENKOU_B,
        displacement=DEFAULT_DISPLACEMENT,
    )

    # span_a and span_b are already displaced forward in the engine
    # cloud_top = max(span_a, span_b), cloud_bot = min(span_a, span_b)
    # We export the individual spans too for TypeScript parity
    # Derive span_a and span_b directly
    high = df["high"]
    low_ = df["low"]

    def _midpoint(h: pd.Series, l: pd.Series, n: int) -> pd.Series:
        return (h.rolling(n, min_periods=n).max() + l.rolling(n, min_periods=n).min()) / 2.0

    tk_raw = _midpoint(high, low_, DEFAULT_TENKAN)
    kj_raw = _midpoint(high, low_, DEFAULT_KIJUN)
    span_a_raw = ((tk_raw + kj_raw) / 2.0).shift(DEFAULT_DISPLACEMENT)
    span_b_raw = _midpoint(high, low_, DEFAULT_SENKOU_B).shift(DEFAULT_DISPLACEMENT)
    # chikou: close displaced -displacement (lagging span, plotted backward)
    chikou_raw = close.shift(-DEFAULT_DISPLACEMENT)

    return {
        "tenkan": _series_to_list(tenkan),
        "kijun": _series_to_list(kijun),
        "span_a": _series_to_list(span_a_raw),
        "span_b": _series_to_list(span_b_raw),
        "chikou": _series_to_list(chikou_raw),
        "_params": {
            "tenkan": DEFAULT_TENKAN,
            "kijun": DEFAULT_KIJUN,
            "senkou_b": DEFAULT_SENKOU_B,
            "displacement": DEFAULT_DISPLACEMENT,
        },
    }


# ---------------------------------------------------------------------------
# Ribbon EMA computation
# ---------------------------------------------------------------------------

def _compute_ribbon(df: pd.DataFrame) -> dict[str, list[float | None]]:
    """Compute ribbon EMA line values using engine.dannytrades._ema / ribbon_trend.

    Returns dict: fast_ema (span=20), slow_ema (span=50), ribbon_state.
    """
    from engine.dannytrades import ribbon_trend, _ema, CFG  # noqa: PLC0415

    close = df["close"]
    fast_n = CFG["ribbon_fast"]   # 20
    slow_n = CFG["ribbon_slow"]   # 50

    fast_ema = _ema(close, fast_n)
    slow_ema = _ema(close, slow_n)
    ribbon_state = ribbon_trend(close)

    return {
        "fast_ema": _series_to_list(fast_ema),
        "slow_ema": _series_to_list(slow_ema),
        "ribbon_state": _series_to_list(ribbon_state),
        "_params": {
            "fast_span": fast_n,
            "slow_span": slow_n,
            "slope_win": CFG["ribbon_slope_win"],
        },
    }


# ---------------------------------------------------------------------------
# RSI computation (three periods)
# ---------------------------------------------------------------------------

def _compute_rsi(df: pd.DataFrame) -> dict[str, list[float | None]]:
    """Compute RSI(7), RSI(14), RSI(21) using the canonical engine.canon.rsi.

    Wilder RSI with SMA-seeded RMA (same as Pine ta.rsi).
    """
    from engine.canon import rsi as _canon_rsi  # noqa: PLC0415

    close = df["close"]
    return {
        "rsi_7": _series_to_list(_canon_rsi(close, n=7)),
        "rsi_14": _series_to_list(_canon_rsi(close, n=14)),
        "rsi_21": _series_to_list(_canon_rsi(close, n=21)),
        "_params": {"periods": [7, 14, 21], "type": "wilder_sma_seeded_rma"},
    }


# ---------------------------------------------------------------------------
# Bollinger Bands computation
# ---------------------------------------------------------------------------

def _compute_bollinger(df: pd.DataFrame) -> dict[str, list[float | None]]:
    """Compute Bollinger Bands: upper, mid, lower.

    mid = SMA(close, 20), sd = rolling_std(close, 20, ddof=1),
    upper = mid + 2*sd, lower = mid - 2*sd.
    """
    from engine.bollinger_event_signals import _bb_bands  # noqa: PLC0415

    upper, mid, lower = _bb_bands(df, n=20, k=2.0)
    return {
        "upper": _series_to_list(upper),
        "mid": _series_to_list(mid),
        "lower": _series_to_list(lower),
        "_params": {"n": 20, "k": 2.0, "ddof": 1},
    }


# ---------------------------------------------------------------------------
# Indicators M2 computation (VWAP / Volume Profile)
# ---------------------------------------------------------------------------

def _compute_m2(df: pd.DataFrame) -> dict[str, Any]:
    """Compute Indicators M2 values using engine.indicators_m2.

    Returns dict with full-length arrays (null during warmup) for:
      rolling_vwap_n20      : rolling VWAP, n=20
      week_anchored_vwap    : week-anchored VWAP (resets each W-FRI period)
      anchored_vwap_pos50   : anchored VWAP from positional index 50 inclusive
      rolling_poc_w126_b24  : rolling POC (window=126, bins=24)
      volume_profile_final  : volume_profile dict for the full 500-bar window

    All values are daily-bar approximations over typical price (H+L+C)/3.
    """
    from engine.indicators_m2 import (  # noqa: PLC0415
        rolling_vwap,
        week_anchored_vwap,
        anchored_vwap,
        rolling_poc,
        volume_profile,
    )

    rv = rolling_vwap(df, n=20)
    wv = week_anchored_vwap(df)
    av = anchored_vwap(df, anchor=50)
    rp = rolling_poc(df, window=126, bins=24)

    # Final-bar volume profile over the full available window (all 500 bars)
    vp = volume_profile(df, window=len(df), bins=24)
    # Serialize volume_profile dict: convert numpy floats to plain Python floats for JSON
    if vp is not None:
        vp_serialized = {
            "poc": float(vp["poc"]),
            "va_low": float(vp["va_low"]),
            "va_high": float(vp["va_high"]),
            "total_volume": float(vp["total_volume"]),
            "bin_edges": [float(x) for x in vp["bin_edges"]],
            "bin_volumes": [float(x) for x in vp["bin_volumes"]],
            "window_used": int(vp["window_used"]),
        }
    else:
        vp_serialized = None

    return {
        "rolling_vwap_n20": _series_to_list(rv),
        "week_anchored_vwap": _series_to_list(wv),
        "anchored_vwap_pos50": _series_to_list(av),
        "rolling_poc_w126_b24": _series_to_list(rp),
        "volume_profile_final": vp_serialized,
        "_params": {
            "rolling_vwap_n": 20,
            "week_anchored_vwap_period": "W-FRI",
            "anchored_vwap_anchor_pos": 50,
            "rolling_poc_window": 126,
            "rolling_poc_bins": 24,
            "volume_profile_window": len(df),
            "volume_profile_bins": 24,
            "typical_price": "(H+L+C)/3",
            "note": "Daily-bar approximation over typical price — not intraday-true VWAP",
        },
    }


# ---------------------------------------------------------------------------
# OHLCV serializer
# ---------------------------------------------------------------------------

def _ohlcv_to_fixture(df: pd.DataFrame) -> dict[str, Any]:
    """Serialize OHLCV DataFrame to fixture dict."""
    return {
        "n_bars": len(df),
        "rng_seed": _RNG_SEED,
        "date_start": str(df.index[0].date()),
        "date_end": str(df.index[-1].date()),
        "freq": "B",
        "dates": [str(d.date()) for d in df.index],
        "open": list(df["open"].round(6)),
        "high": list(df["high"].round(6)),
        "low": list(df["low"].round(6)),
        "close": list(df["close"].round(6)),
        "volume": list(df["volume"].astype(int)),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_fixtures(output_dir: Path) -> None:
    """Generate all parity fixtures and write to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Generating synthetic OHLCV (seed=%d, n=%d bars)…", _RNG_SEED, _N_BARS)
    df = _generate_ohlcv(n=_N_BARS, seed=_RNG_SEED)
    log.info("Date range: %s → %s", df.index[0].date(), df.index[-1].date())

    # OHLCV fixture
    ohlcv_fixture = _ohlcv_to_fixture(df)
    ohlcv_path = output_dir / "ohlcv.json"
    with open(ohlcv_path, "w") as fh:
        json.dump(ohlcv_fixture, fh, indent=2)
    log.info("Wrote %s", ohlcv_path)

    # Ichimoku
    log.info("Computing Ichimoku lines…")
    ichimoku = _compute_ichimoku(df)
    ich_path = output_dir / "expected_ichimoku.json"
    with open(ich_path, "w") as fh:
        json.dump(ichimoku, fh, indent=2)
    log.info("Wrote %s", ich_path)

    # Ribbon
    log.info("Computing ribbon EMAs…")
    ribbon = _compute_ribbon(df)
    rib_path = output_dir / "expected_ribbon.json"
    with open(rib_path, "w") as fh:
        json.dump(ribbon, fh, indent=2)
    log.info("Wrote %s", rib_path)

    # RSI
    log.info("Computing RSI(7/14/21)…")
    rsi_data = _compute_rsi(df)
    rsi_path = output_dir / "expected_rsi.json"
    with open(rsi_path, "w") as fh:
        json.dump(rsi_data, fh, indent=2)
    log.info("Wrote %s", rsi_path)

    # Bollinger
    log.info("Computing Bollinger Bands…")
    bb_data = _compute_bollinger(df)
    bb_path = output_dir / "expected_bollinger.json"
    with open(bb_path, "w") as fh:
        json.dump(bb_data, fh, indent=2)
    log.info("Wrote %s", bb_path)

    # Indicators M2 (VWAP / Volume Profile)
    log.info("Computing Indicators M2 (VWAP / Volume Profile)…")
    m2_data = _compute_m2(df)
    m2_path = output_dir / "expected_m2.json"
    with open(m2_path, "w") as fh:
        json.dump(m2_data, fh, indent=2)
    log.info("Wrote %s", m2_path)

    log.info("All fixtures written to %s", output_dir)
    print(f"\n[build_tech_parity_fixtures] {_N_BARS} bars, seed={_RNG_SEED}")
    print(f"  ohlcv.json:              {ohlcv_path}")
    print(f"  expected_ichimoku.json:  {ich_path}")
    print(f"  expected_ribbon.json:    {rib_path}")
    print(f"  expected_rsi.json:       {rsi_path}")
    print(f"  expected_bollinger.json: {bb_path}")
    print(f"  expected_m2.json:        {m2_path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic parity fixtures for Tech Lab indicators (TLT-R5).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args(argv)
    build_fixtures(args.output_dir)


if __name__ == "__main__":
    main()
