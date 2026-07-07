"""Tests for scripts.grade_breadth_divergence — maturity gating + idempotence.

Synthetic fixtures only; never reads or writes the real tracked parquet.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.grade_breadth_divergence import grade_matured_rows, _log_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trading_days_ago(n: int) -> str:
    """Return an ISO date string that is approximately n trading days before today.
    Uses calendar days * 1.4 as a safe overcount, then counts back precisely."""
    d = date.today()
    counted = 0
    step = timedelta(days=1)
    while counted < n:
        d -= step
        if d.weekday() < 5:  # Mon–Fri
            counted += 1
    return d.isoformat()


def _make_level(seed: int = 42, extra_days: int = 40) -> pd.Series:
    """Business-day level series ending extra_days business days after today.

    Long enough to cover the stamp_date (30 bdays ago) with an h21 forward
    window. Start well before 30 bdays ago so realized_fwd_dd has an anchor.
    """
    rng = np.random.default_rng(seed)
    # end index = today + extra_days bdays (so forward window is always present)
    end = pd.Timestamp.today().normalize() + pd.offsets.BDay(extra_days)
    start = end - pd.offsets.BDay(400)
    idx = pd.bdate_range(start, end)
    n_days = len(idx)
    closes = 100.0 * np.cumprod(1 + rng.normal(-0.001, 0.01, n_days))
    return pd.Series(closes.clip(min=0.01), index=idx)


def _ohlcv_for(ticker: str, lvl: pd.Series, tmp_path: Path) -> None:
    """Write a synthetic OHLCV parquet for a ticker aligned to lvl."""
    ohlcv_dir = tmp_path / "data" / "baskets" / "ohlcv"
    ohlcv_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "open": lvl.values,
        "high": lvl.values * 1.01,
        "low": lvl.values * 0.99,
        "close": lvl.values,
        "volume": 1e6,
    }, index=lvl.index)
    df.to_parquet(ohlcv_dir / f"{ticker}.parquet")


def _membership_json(tmp_path: Path, baskets: dict[str, list[str]],
                     added: str = "2024-01-01") -> None:
    """Write (or update) membership.json with one or more baskets.

    baskets: {basket_id: [ticker, ...]}
    Reads existing file if present so multiple calls accumulate entries.
    """
    mem_dir = tmp_path / "data" / "baskets"
    mem_dir.mkdir(parents=True, exist_ok=True)
    p = mem_dir / "membership.json"
    existing: dict = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text()).get("baskets", {})
        except Exception:
            pass
    for basket_id, tickers in baskets.items():
        members = [{"ticker": t, "added": added, "removed": None} for t in tickers]
        existing[basket_id] = {"members": members}
    mem = {"version": 1, "baskets": existing}
    p.write_text(json.dumps(mem))


def _forward_log(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "data" / "breadth_divergence" / "forward_log.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    # ensure required columns even if some are missing in caller
    for col in ["date", "basket_id", "region", "risk", "band", "basket_off_high",
                "pct_above_50", "label_at_stamp"]:
        if col not in df.columns:
            df[col] = None
    df.to_parquet(p, index=False)
    return p


# ---------------------------------------------------------------------------
# Test 1: unmatured row is NOT graded
# ---------------------------------------------------------------------------

def test_unmatured_row_not_graded(tmp_path: Path) -> None:
    """A stamp from yesterday must not be graded (h21 not reached)."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    _forward_log(tmp_path, [{"date": yesterday, "basket_id": "mag7", "region": "us",
                              "risk": 0.7, "band": "high",
                              "basket_off_high": -0.02, "pct_above_50": 0.4,
                              "label_at_stamp": "neutral"}])
    lvl = _make_level(seed=1)
    _ohlcv_for("AAPL", lvl, tmp_path)
    _ohlcv_for("MSFT", lvl, tmp_path)
    _ohlcv_for("GOOGL", lvl, tmp_path)
    _membership_json(tmp_path, {"mag7": ["AAPL", "MSFT", "GOOGL"]})

    n = grade_matured_rows(root=tmp_path)
    assert n == 0, "unmatured row must not be graded"

    df = pd.read_parquet(_log_path(tmp_path))
    assert "fwd_dd" not in df.columns or df["fwd_dd"].isna().all()


# ---------------------------------------------------------------------------
# Test 2: matured row IS graded
# ---------------------------------------------------------------------------

def test_matured_row_is_graded(tmp_path: Path) -> None:
    """A stamp from 30+ trading days ago must receive an fwd_dd grade."""
    stamp_date = _trading_days_ago(30)
    _forward_log(tmp_path, [{"date": stamp_date, "basket_id": "b1", "region": "us",
                              "risk": 0.8, "band": "high",
                              "basket_off_high": -0.03, "pct_above_50": 0.3,
                              "label_at_stamp": "fading"}])
    lvl = _make_level(seed=42)
    for t in ["A", "B", "C"]:
        _ohlcv_for(t, lvl, tmp_path)
    _membership_json(tmp_path, {"b1": ["A", "B", "C"]})

    n = grade_matured_rows(root=tmp_path)
    assert n == 1, f"expected 1 graded row, got {n}"

    df = pd.read_parquet(_log_path(tmp_path))
    assert "fwd_dd" in df.columns
    assert df["fwd_dd"].notna().any(), "fwd_dd should be non-null for the graded row"
    fdd = df.loc[df["basket_id"] == "b1", "fwd_dd"].iloc[0]
    assert isinstance(fdd, float), f"fwd_dd should be float, got {type(fdd)}"
    assert -1.0 <= fdd <= 0.0, f"fwd_dd must be in [-1, 0], got {fdd}"


# ---------------------------------------------------------------------------
# Test 3: idempotence — already-graded rows are not re-graded
# ---------------------------------------------------------------------------

def test_idempotent_second_run(tmp_path: Path) -> None:
    """Running the grader twice must not change already-graded rows."""
    stamp_date = _trading_days_ago(30)
    _forward_log(tmp_path, [{"date": stamp_date, "basket_id": "b2", "region": "us",
                              "risk": 0.6, "band": "elevated",
                              "basket_off_high": -0.04, "pct_above_50": 0.45,
                              "label_at_stamp": "neutral"}])
    lvl = _make_level(seed=7)
    for t in ["X", "Y", "Z"]:
        _ohlcv_for(t, lvl, tmp_path)
    _membership_json(tmp_path, {"b2": ["X", "Y", "Z"]})

    # First run
    n1 = grade_matured_rows(root=tmp_path)
    assert n1 == 1

    df1 = pd.read_parquet(_log_path(tmp_path))
    fdd_first = float(df1.loc[df1["basket_id"] == "b2", "fwd_dd"].iloc[0])

    # Second run — should grade 0 new rows and leave fwd_dd unchanged
    n2 = grade_matured_rows(root=tmp_path)
    assert n2 == 0, "second run must not re-grade already-graded rows"

    df2 = pd.read_parquet(_log_path(tmp_path))
    fdd_second = float(df2.loc[df2["basket_id"] == "b2", "fwd_dd"].iloc[0])
    assert abs(fdd_first - fdd_second) < 1e-12, "fwd_dd must not change on re-run"


# ---------------------------------------------------------------------------
# Test 4: mixed matured + unmatured — only matured rows graded
# ---------------------------------------------------------------------------

def test_mixed_rows_only_matured_graded(tmp_path: Path) -> None:
    """When the log has both matured and unmatured rows, only matured are graded."""
    old_date = _trading_days_ago(30)
    new_date = (date.today() - timedelta(days=1)).isoformat()
    _forward_log(tmp_path, [
        {"date": old_date, "basket_id": "bA", "region": "us",
         "risk": 0.7, "band": "high", "basket_off_high": -0.02,
         "pct_above_50": 0.3, "label_at_stamp": "neutral"},
        {"date": new_date, "basket_id": "bB", "region": "us",
         "risk": 0.5, "band": "elevated", "basket_off_high": -0.04,
         "pct_above_50": 0.5, "label_at_stamp": "neutral"},
    ])
    lvl = _make_level(seed=3)
    for t in ["P", "Q", "R"]:
        _ohlcv_for(t, lvl, tmp_path)
    _membership_json(tmp_path, {"bA": ["P", "Q", "R"], "bB": ["P", "Q", "R"]})

    n = grade_matured_rows(root=tmp_path)
    assert n == 1, "only the matured row should be graded"

    df = pd.read_parquet(_log_path(tmp_path))
    assert df.loc[df["basket_id"] == "bA", "fwd_dd"].notna().all(), "matured row must be graded"
    assert df.loc[df["basket_id"] == "bB", "fwd_dd"].isna().all(), "unmatured row must NOT be graded"


# ---------------------------------------------------------------------------
# Test 5: absent forward_log → graceful return 0
# ---------------------------------------------------------------------------

def test_absent_log_returns_zero(tmp_path: Path) -> None:
    """If the forward_log does not exist, grade_matured_rows returns 0."""
    n = grade_matured_rows(root=tmp_path)
    assert n == 0
