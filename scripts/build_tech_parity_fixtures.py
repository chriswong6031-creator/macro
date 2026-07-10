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

    log.info("All fixtures written to %s", output_dir)
    print(f"\n[build_tech_parity_fixtures] {_N_BARS} bars, seed={_RNG_SEED}")
    print(f"  ohlcv.json:              {ohlcv_path}")
    print(f"  expected_ichimoku.json:  {ich_path}")
    print(f"  expected_ribbon.json:    {rib_path}")
    print(f"  expected_rsi.json:       {rsi_path}")
    print(f"  expected_bollinger.json: {bb_path}")


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
