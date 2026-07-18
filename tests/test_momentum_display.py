"""Tests for engine/momentum_display.py.

Observed production schemas (2026-07-17):
  _closes_cache.parquet  : DatetimeIndex (datetime64[ms]), wide matrix of floats,
                           columns are ticker strings (e.g. 'AAPL'); shape ~(335, 509)
  constituents.parquet   : Index(str) named 'symbol', columns=['name', 'sector']
  MTUM.parquet / SPY.parquet : DatetimeIndex (datetime64[ms]),
                               columns=['close_price', 'close', 'volume']

All synthetic fixtures below mirror these exact types so the production read-paths
exercise the same code as the test paths.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import momentum_display as md


# ---------------------------------------------------------------------------
# Fixture helpers  — prod-shaped synthetic data
# ---------------------------------------------------------------------------

def _bdate_ms(n: int, start: str = "2023-01-01") -> pd.DatetimeIndex:
    """Business-day DatetimeIndex with dtype datetime64[ms], matching prod."""
    idx = pd.bdate_range(start, periods=n)
    return idx.astype("datetime64[ms]")


def _make_closes(n_rows: int, tickers: list[str], *, seed: int = 42) -> pd.DataFrame:
    """Wide close matrix — DatetimeIndex(datetime64[ms]) × ticker str columns."""
    rng = np.random.default_rng(seed)
    idx = _bdate_ms(n_rows)
    prices = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, size=(n_rows, len(tickers))), axis=0)
    df = pd.DataFrame(prices, index=idx, columns=tickers)
    return df


def _make_constituents(tickers: list[str], sectors: list[str]) -> pd.DataFrame:
    """ticker→sector mapping, index named 'symbol' with str dtype, col 'sector'."""
    idx = pd.Index(tickers, dtype="str", name="symbol")
    df = pd.DataFrame(
        {"name": tickers, "sector": sectors},
        index=idx,
    )
    return df


def _make_yahoo(n_rows: int, *, seed: int = 7, start: str = "2023-01-01") -> pd.DataFrame:
    """Prod-shaped Yahoo parquet: DatetimeIndex(datetime64[ms]), cols=[close_price, close, volume]."""
    rng = np.random.default_rng(seed)
    idx = _bdate_ms(n_rows, start)
    prices = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, size=n_rows))
    df = pd.DataFrame(
        {"close_price": prices, "close": prices, "volume": rng.integers(1_000, 1_000_000, n_rows).astype(float)},
        index=idx,
    )
    df.index.name = "Date"
    return df


def _write_tmp(tmp: Path, closes: pd.DataFrame, constituents: pd.DataFrame,
               mtum: pd.DataFrame | None, spy: pd.DataFrame | None) -> tuple[Path, Path, Path, Path]:
    cp = tmp / "_closes_cache.parquet"
    kp = tmp / "constituents.parquet"
    mp = tmp / "MTUM.parquet"
    sp = tmp / "SPY.parquet"
    closes.to_parquet(cp)
    constituents.to_parquet(kp)
    if mtum is not None:
        mtum.to_parquet(mp)
    if spy is not None:
        spy.to_parquet(sp)
    return cp, kp, mp, sp


# ---------------------------------------------------------------------------
# Tickers / sectors
# ---------------------------------------------------------------------------

SECTORS = ["Technology", "Health Care", "Financials", "Consumer Discretionary", "Industrials"]
TICKERS = [f"T{i:03d}" for i in range(50)]
TICK_SECTORS = [SECTORS[i % len(SECTORS)] for i in range(len(TICKERS))]


# ---------------------------------------------------------------------------
# Core decile math
# ---------------------------------------------------------------------------

def test_top_decile_contains_highest_momentum(tmp_path):
    """Top-decile sample should be the highest 12-1 momentum tickers.

    The 12-1 return is px[iloc[-22]] / px[iloc[-253]] - 1.  To guarantee T000
    is the clear winner, set its price at the px_now row to 10x its px_old value
    — leaving all other rows untouched avoids raising the baseline price level.
    """
    closes = _make_closes(300, TICKERS)
    # Set px_now for T000 = 10 × its px_old → return = 900 %, far above any peer
    px_old_val = float(closes["T000"].iloc[-253])
    closes.loc[closes.index[-22], "T000"] = px_old_val * 10
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)

    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)
    result = md.compute_momentum_display(cp, kp, mp, sp)

    assert result is not None
    assert result["top_decile"]["sample"][0] == "T000", "highest-return ticker must lead sample"


def test_bottom_decile_has_lower_mean_than_top(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    sp_ = result["spread"]
    assert sp_["top_decile_mean_pct"] > sp_["bottom_decile_mean_pct"]
    assert sp_["spread_pp"] > 0


def test_spread_pp_equals_top_minus_bottom(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    cp, kp, _, _ = _write_tmp(tmp_path, closes, constituents, None, None)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    mp = tmp_path / "MTUM.parquet"
    sp = tmp_path / "SPY.parquet"
    mtum.to_parquet(mp)
    spy.to_parquet(sp)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    spr = result["spread"]
    expected = round(spr["top_decile_mean_pct"] - spr["bottom_decile_mean_pct"], 2)
    assert abs(spr["spread_pp"] - expected) < 0.01


# ---------------------------------------------------------------------------
# Sector concentration
# ---------------------------------------------------------------------------

def test_top_sector_identified_correctly(tmp_path):
    """Tickers with Technology sector should dominate when pumped.

    Pump 20 Technology tickers by setting their px_now = 10 × px_old so they
    all have ~900 % 12-1 returns, dominating the top decile.
    """
    tech_tickers = [f"TECH{i}" for i in range(20)]
    other_tickers = [f"OTH{i}" for i in range(30)]
    all_tickers = tech_tickers + other_tickers
    sectors = ["Technology"] * 20 + ["Financials"] * 30

    closes = _make_closes(300, all_tickers)
    # Pump tech tickers: set px_now (iloc[-22]) = 10 × px_old (iloc[-253])
    for t in tech_tickers:
        closes.loc[closes.index[-22], t] = float(closes[t].iloc[-253]) * 10

    constituents = _make_constituents(all_tickers, sectors)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    assert result["top_decile"]["top_sector"] == "Technology"
    assert result["top_decile"]["top_sector_share_pct"] > 50.0


def test_unknown_sector_maps_to_other(tmp_path):
    """Tickers absent from constituents get 'Other' sector."""
    unknown = [f"UNK{i}" for i in range(20)]
    known = [f"KN{i}" for i in range(30)]
    all_tickers = unknown + known

    closes = _make_closes(300, all_tickers)
    # Only register the known tickers in constituents
    constituents = _make_constituents(known, ["Industrials"] * 30)

    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    sector_names = [r["sector"] for r in result["top_decile"]["sectors"]]
    assert "Other" in sector_names


def test_sector_shares_sum_to_lte_100(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    total = sum(r["share_pct"] for r in result["top_decile"]["sectors"])
    # top-3 sectors, so total ≤ 100
    assert total <= 100.1


# ---------------------------------------------------------------------------
# Pulse block
# ---------------------------------------------------------------------------

def test_pulse_present_when_both_yahoo_files_exist(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    assert result["pulse"] is not None
    assert "mtum_spy_20d_pct" in result["pulse"]
    assert "mtum_spy_60d_pct" in result["pulse"]


def test_pulse_absent_when_mtum_missing(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    spy = _make_yahoo(300, seed=99)
    cp = tmp_path / "_closes_cache.parquet"
    kp = tmp_path / "constituents.parquet"
    sp = tmp_path / "SPY.parquet"
    closes.to_parquet(cp)
    constituents.to_parquet(kp)
    spy.to_parquet(sp)
    # MTUM file deliberately not written
    mp = tmp_path / "MTUM.parquet"

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    assert result["pulse"] is None


def test_pulse_20d_and_60d_are_floats(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    pulse = result["pulse"]
    assert isinstance(pulse["mtum_spy_20d_pct"], float)
    assert isinstance(pulse["mtum_spy_60d_pct"], float)


# ---------------------------------------------------------------------------
# Degrade paths
# ---------------------------------------------------------------------------

def test_returns_none_when_closes_missing(tmp_path):
    result = md.compute_momentum_display(
        tmp_path / "nonexistent.parquet",
        tmp_path / "c.parquet",
        tmp_path / "m.parquet",
        tmp_path / "s.parquet",
    )
    assert result is None


def test_short_cache_returns_pulse_only_payload(tmp_path):
    """When closes has <253 rows, top_decile and spread are None; pulse may exist."""
    closes = _make_closes(100, TICKERS)  # only 100 rows — too short for 12-1 mom
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    assert result["top_decile"] is None
    assert result["spread"] is None
    # pulse may exist (yahoo is long enough independently)
    assert "pulse" in result


def test_missing_constituents_degrades_gracefully(tmp_path):
    """Absent constituents file → sectors label as Other, still returns a result."""
    closes = _make_closes(300, TICKERS)
    cp = tmp_path / "_closes_cache.parquet"
    closes.to_parquet(cp)
    kp = tmp_path / "nonexistent_constituents.parquet"

    result = md.compute_momentum_display(cp, kp, tmp_path / "M.parquet", tmp_path / "S.parquet")
    assert result is not None
    # top_decile should still be populated (sector info degrades to "Other")
    assert result["top_decile"] is not None
    sector_names = [r["sector"] for r in result["top_decile"]["sectors"]]
    assert sector_names == ["Other"]


# ---------------------------------------------------------------------------
# Schema and disclosure guards
# ---------------------------------------------------------------------------

def test_output_contains_unscored_true(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    assert result.get("unscored") is True


def test_schema_key_is_v1(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result["schema"] == "momentum_display.v1"


def test_disclosure_keys_present(tmp_path):
    closes = _make_closes(300, TICKERS)
    constituents = _make_constituents(TICKERS, TICK_SECTORS)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert "disclosure_en" in result
    assert "disclosure_zh" in result
    assert len(result["disclosure_en"]) > 20
    assert len(result["disclosure_zh"]) > 10


def test_as_of_matches_last_close_date(tmp_path):
    closes = _make_closes(300, TICKERS)
    cp = tmp_path / "_closes_cache.parquet"
    closes.to_parquet(cp)

    result = md.compute_momentum_display(
        cp,
        tmp_path / "no_constituents.parquet",
        tmp_path / "M.parquet",
        tmp_path / "S.parquet",
    )
    assert result is not None
    expected_as_of = closes.index[-1].strftime("%Y-%m-%d")
    assert result["as_of"] == expected_as_of


def test_universe_counts_match_input(tmp_path):
    tickers = [f"X{i}" for i in range(30)]
    closes = _make_closes(300, tickers)
    constituents = _make_constituents(tickers, ["Technology"] * 30)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result["universe"]["n_tickers"] == 30


def test_top_decile_sample_max_10_tickers(tmp_path):
    """sample field must contain at most 10 tickers regardless of universe size."""
    # 200 tickers → decile = 20 → sample capped at 10
    tickers = [f"BIG{i:03d}" for i in range(200)]
    sectors = [SECTORS[i % len(SECTORS)] for i in range(200)]
    closes = _make_closes(300, tickers)
    constituents = _make_constituents(tickers, sectors)
    mtum = _make_yahoo(300)
    spy = _make_yahoo(300, seed=99)
    cp, kp, mp, sp = _write_tmp(tmp_path, closes, constituents, mtum, spy)

    result = md.compute_momentum_display(cp, kp, mp, sp)
    assert result is not None
    assert len(result["top_decile"]["sample"]) <= 10
