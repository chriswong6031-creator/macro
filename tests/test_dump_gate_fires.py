"""Tests for scripts/research/dump_gate_fires.py.

Covers:
  (a) AAPL known-answer sanity: the AAPL parquet in data/replay/ must register the
      expected ~194 fires (±10% tolerance), guards against silent regressions.
  (b) Corrupt-input fixture (>=MIN_HISTORY bars, string close column) → recorded as
      error in manifest (guards Finding-1 fix: silent-zero trap).
  (c) Manifest fires sum == parquet row count (structural consistency).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure repo root is on path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.research.dump_gate_fires import _process_ticker, run
from engine.confluence_tiers import MIN_HISTORY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close(n: int, seed: int = 42) -> pd.Series:
    """Synthetic trending close series of length n with a DatetimeIndex."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    prices = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n)))
    return pd.Series(prices, index=idx, name="close")


# ---------------------------------------------------------------------------
# Finding-1 guard: >=MIN_HISTORY bars corrupt input → error (not warning / zero)
# ---------------------------------------------------------------------------

def test_corrupt_input_recorded_as_error(tmp_path: Path) -> None:
    """A parquet with >=MIN_HISTORY bars but a STRING close column must be recorded
    as error=<non-None>, not as a clean zero-fire ticker.

    This guards the silent-zero trap: tier_stream returns empty on a corrupt input;
    before the fix the worker would set error=None and warning=... which caused the
    summary error-count to undercount.
    """
    ticker = "CORRUPT_TEST"
    n = MIN_HISTORY + 50  # deliberately above the thin-history gate

    # Build a parquet with a string 'close' column — tier_stream will fail / return empty
    idx = pd.bdate_range("2015-01-01", periods=n)
    df = pd.DataFrame({"close": ["bad"] * n}, index=idx)
    pq_path = tmp_path / f"{ticker}.parquet"
    df.to_parquet(pq_path)

    result = _process_ticker((str(pq_path), "close", "deep"))

    assert result["ticker"] == ticker
    assert result["fires"] == 0
    # The key assertion: error must be truthy (non-None, non-empty)
    assert result.get("error"), (
        f"Expected a non-None error for a corrupt >=MIN_HISTORY ticker, got: {result}"
    )
    # No 'warning' key should survive — the fix routes this to 'error'
    assert not result.get("warning"), (
        f"'warning' key should not be set after the fix; got: {result}"
    )


# ---------------------------------------------------------------------------
# Finding-1 guard: thin-history ticker → still recorded as error (unchanged)
# ---------------------------------------------------------------------------

def test_thin_history_recorded_as_error(tmp_path: Path) -> None:
    """A parquet with <MIN_HISTORY bars → error='thin history (...)' (unchanged behaviour)."""
    ticker = "THIN_TEST"
    n = MIN_HISTORY - 1

    close = _make_close(n)
    df = pd.DataFrame({"close": close.values}, index=close.index)
    pq_path = tmp_path / f"{ticker}.parquet"
    df.to_parquet(pq_path)

    result = _process_ticker((str(pq_path), "close", "deep"))

    assert result["fires"] == 0
    assert result.get("error"), f"Thin-history ticker must have error set; got: {result}"
    assert "thin" in result["error"].lower()


# ---------------------------------------------------------------------------
# Structural consistency: manifest fires sum == parquet row count
# ---------------------------------------------------------------------------

def test_manifest_sum_matches_parquet_row_count(tmp_path: Path) -> None:
    """After run(), sum(manifest[t]['fires']) must equal len(parquet)."""
    # Build a small synthetic panel: 3 tickers, 2 with enough history, 1 thin
    panel_dir = tmp_path / "stocks"
    panel_dir.mkdir()

    for name in ["SYN_A", "SYN_B"]:
        close = _make_close(600)
        df = pd.DataFrame({"close": close.values}, index=close.index)
        (panel_dir / f"{name}.parquet").write_bytes(
            b""  # placeholder — overwrite properly
        )
        df.to_parquet(panel_dir / f"{name}.parquet")

    # Thin ticker
    close_thin = _make_close(50)
    df_thin = pd.DataFrame({"close": close_thin.values}, index=close_thin.index)
    df_thin.to_parquet(panel_dir / "SYN_THIN.parquet")

    from scripts.research.dump_gate_fires import PANEL_CONFIGS, run as _run

    # Patch PANEL_CONFIGS to point at our synthetic dir
    original_cfg = PANEL_CONFIGS.get("deep", {}).get("glob")
    PANEL_CONFIGS["deep"] = {"glob": "stocks/*.parquet", "col": "close"}

    out_parquet = tmp_path / "gate_fires_deep.parquet"
    manifest_path = tmp_path / "gate_fires_deep_manifest.json"

    try:
        _run(
            panel="deep",
            data_root=tmp_path,
            out_parquet=out_parquet,
            manifest_path=manifest_path,
            workers=1,
            resume=False,
            force=False,
        )
    finally:
        # Restore original config
        if original_cfg is not None:
            PANEL_CONFIGS["deep"] = {"glob": original_cfg, "col": "close"}

    with open(manifest_path) as f:
        manifest = json.load(f)

    manifest_total_fires = sum(v["fires"] for v in manifest.values())

    if out_parquet.exists() and out_parquet.stat().st_size > 0:
        fire_df = pd.read_parquet(out_parquet)
        parquet_rows = len(fire_df)
    else:
        parquet_rows = 0

    assert manifest_total_fires == parquet_rows, (
        f"Manifest fires sum ({manifest_total_fires}) != parquet rows ({parquet_rows})"
    )

    # Thin ticker must be in manifest as error
    thin_entry = manifest.get("SYN_THIN", {})
    assert thin_entry.get("error"), f"Thin ticker must have error set; got: {thin_entry}"


# ---------------------------------------------------------------------------
# AAPL known-answer: ~194 fires (±10%)
# ---------------------------------------------------------------------------

# Prefer the replay parquet (committed artifact) if present; fall back to the
# deep-panel stocks parquet which covers the same close history.
AAPL_REPLAY_PATH = REPO_ROOT / "data" / "replay" / "AAPL.parquet"
AAPL_STOCKS_PATH = REPO_ROOT / "data" / "stocks" / "AAPL.parquet"
AAPL_PATH = AAPL_REPLAY_PATH if AAPL_REPLAY_PATH.exists() else AAPL_STOCKS_PATH
AAPL_EXPECTED_FIRES = 194
AAPL_TOLERANCE = 0.10  # ±10%


@pytest.mark.skipif(
    not AAPL_PATH.exists(),
    reason=f"AAPL parquet not present at {AAPL_REPLAY_PATH} or {AAPL_STOCKS_PATH}",
)
def test_aapl_known_answer() -> None:
    """AAPL gate-fire count must be within ±10% of 194 (the builder-verified count).

    This is a regression guard: if confluence_tiers or the dumper logic changes in a
    way that silently shifts the fire count, this test catches it.
    """
    result = _process_ticker((str(AAPL_PATH), "close", "deep"))

    assert result.get("error") is None, (
        f"AAPL must process without error; got: {result.get('error')}"
    )

    fires = result["fires"]
    lo = int(AAPL_EXPECTED_FIRES * (1 - AAPL_TOLERANCE))
    hi = int(AAPL_EXPECTED_FIRES * (1 + AAPL_TOLERANCE))
    assert lo <= fires <= hi, (
        f"AAPL fires={fires} outside expected [{lo}, {hi}] "
        f"(expected ~{AAPL_EXPECTED_FIRES} ±{int(AAPL_TOLERANCE*100)}%)"
    )
