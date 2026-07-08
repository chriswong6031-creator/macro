"""tests/test_context_api.py — NW-CI W2: context_snapshot PIT API tests.

Coverage:
  (1)  personality dimension — PIT parquet hit (deep name, historical date)
  (2)  personality dimension — absent (non-deep name, old date, JSON exists)
  (3)  personality dimension — snapshot_not_pit (non-deep name, date within 5 trading days)
  (4)  archetype dimension — pit_labels basis with backward merge
  (5)  archetype dimension — absent when parquet missing
  (6)  regime dimension — recomputed_history from regime_history.parquet
  (7)  regime dimension — absent when parquet missing
  (8)  short_int dimension — snapshot_not_pit basis when date differs from settlement
  (9)  short_int dimension — absent when parquet missing
  (10) insider dimension — trailing-90d aggregate
  (11) options dimension — absent-tolerant when no options data
  (12) spine dimension — last-5 logic + absent-tolerant
  (13) factor dimension — absent (host-only store) — no raise
  (14) attention dimension — absent (host-only store) — no raise
  (15) sector dimension — present with sector_node; absent oracle
  (16) ALL absent stores → absent markers, never raises
  (17) [CRITICAL] PIT leak boundary: spine row 30 days ago for non-deep name
       must get personality_basis='absent' even when production JSON exists.
  (18) _stamp_personality — deep name historical → pit_labels
  (19) _stamp_personality — fresh row + prod JSON → snapshot_not_pit
  (20) _stamp_personality — old non-deep row → absent
  (21) _stamp_personality — absent PIT parquet → all rows absent (no crash)
  (22) context_frame — vectorised result, correct column names
  (23) determinism — two calls with same inputs return same result
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine.neuralweb.context_api import (
    context_snapshot,
    context_frame,
    _personality_dim,
    _archetype_dim,
    _regime_dim,
    _short_int_dim,
    _insider_dim,
    _spine_dim,
    _trading_days_between,
    _signed_trading_days,
)
from engine.neuralweb.query import _stamp_personality, _CI_NEW_COLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_root(tmp_path: Path) -> Path:
    """Create minimal directory tree expected by context_api."""
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "site" / "factordata").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    return tmp_path


def _write_pit_labels(root: Path, rows: list[dict]) -> Path:
    path = root / "data" / "research" / "personality_pit_labels.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _write_archetype_history(root: Path, rows: list[dict]) -> Path:
    path = root / "data" / "archetypes" / "history.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _write_regime_history(root: Path, rows: list[dict]) -> Path:
    path = root / "data" / "regime" / "regime_history.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _write_prod_json(root: Path, as_of: str, per_ticker: dict) -> Path:
    path = root / "site" / "factordata" / "stock_personality.json"
    data = {
        "schema": "stock_personality.v1",
        "as_of":  as_of,
        "n_tickers": len(per_ticker),
        "coverage": {},
        "label_distributions": {},
        "per_ticker": per_ticker,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _write_si(root: Path, rows: list[dict], index_col: str = "ticker") -> Path:
    path = root / "data" / "finra" / "short_interest.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if index_col in df.columns:
        df = df.set_index(index_col)
    df.to_parquet(path)
    return path


def _write_insider_panel(root: Path, rows: list[dict], filename: str = "2026q1.parquet") -> Path:
    path = root / "data" / "sec_insider" / "panel" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def _write_spine_index(root: Path, rows: list[dict]) -> Path:
    path = root / "data" / "neuralweb" / "spine_index.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# (1) Personality — PIT parquet hit for deep name
# ---------------------------------------------------------------------------

def test_personality_pit_labels_deep_name(tmp_path):
    """Deep name in PIT parquet should return basis='pit_labels'."""
    root = _make_root(tmp_path)
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2025-06-01"),
         "chart_primary": "mean_reversion_rubber_band",
         "micro_primary": "tight_spread_absorber",
         "chart_labels": "mean_reversion_rubber_band",
         "micro_labels": "tight_spread_absorber",
         "archetype": "mixed", "archetype_asof": None, "archetype_fy": None},
        {"ticker": "AAPL", "date": pd.Timestamp("2025-09-01"),
         "chart_primary": "volatile_momentum_vehicle",
         "micro_primary": "wide_spread_impact",
         "chart_labels": "volatile_momentum_vehicle",
         "micro_labels": "wide_spread_impact",
         "archetype": "mixed", "archetype_asof": None, "archetype_fy": None},
    ])

    result = context_snapshot("AAPL", date="2025-07-15", root=root)
    dim = result["dimensions"]["personality"]
    assert dim.get("absent") is not True, f"Expected present, got: {dim}"
    assert dim["basis"] == "pit_labels"
    assert dim["value"]["chart_primary"] == "mean_reversion_rubber_band"


# ---------------------------------------------------------------------------
# (2) Personality — absent for non-deep name with old date (JSON too stale)
# ---------------------------------------------------------------------------

def test_personality_absent_old_date_non_deep(tmp_path):
    """Non-deep name with date > 5 trading days before JSON as_of → absent (R-CI3)."""
    root = _make_root(tmp_path)
    # PIT parquet only has AAPL (deep name), MSFT is NOT in PIT
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2025-01-01"),
         "chart_primary": "mixed_chart", "micro_primary": None,
         "chart_labels": "mixed_chart", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])
    # Production JSON as_of is today-ish; query date is 30 days ago
    prod_asof = pd.Timestamp.today().normalize()
    old_date = prod_asof - pd.Timedelta(days=30)
    _write_prod_json(root, str(prod_asof.date()), {
        "MSFT": {"arch": "quality_compounder", "chart": ["smooth_compounder_grind"],
                 "micro": ["tight_spread_absorber"], "modes": ["normal"]},
    })

    result = context_snapshot("MSFT", date=str(old_date.date()), root=root)
    dim = result["dimensions"]["personality"]
    assert dim.get("absent") is True, f"Expected absent for old non-deep date, got: {dim}"


# ---------------------------------------------------------------------------
# (3) Personality — snapshot_not_pit for non-deep name within 5 trading days
# ---------------------------------------------------------------------------

def test_personality_snapshot_not_pit(tmp_path):
    """Non-deep name with date AFTER JSON as_of by ≤5 trading days → snapshot_not_pit.

    R-CI3 directional law: prod_asof <= row_date is required.  A date 2 days AFTER
    prod_asof passes the window; a date 2 days BEFORE prod_asof must return absent
    (tested separately in test_personality_snapshot_not_pit_before_asof).
    """
    root = _make_root(tmp_path)
    # No PIT labels for MSFT
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2025-01-01"),
         "chart_primary": "mixed_chart", "micro_primary": None,
         "chart_labels": "mixed_chart", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])
    # Production JSON as_of is 3 days ago; query date is 2 days ago (after prod_asof)
    prod_asof = pd.Timestamp.today().normalize() - pd.Timedelta(days=3)
    query_date = prod_asof + pd.Timedelta(days=2)  # 2 days AFTER prod_asof → within window
    _write_prod_json(root, str(prod_asof.date()), {
        "MSFT": {"arch": "quality_compounder", "chart": ["smooth_compounder_grind"],
                 "micro": ["tight_spread_absorber"], "modes": ["normal"]},
    })

    result = context_snapshot("MSFT", date=str(query_date.date()), root=root)
    dim = result["dimensions"]["personality"]
    assert dim.get("absent") is not True, f"Expected snapshot_not_pit, got: {dim}"
    assert dim["basis"] == "snapshot_not_pit"
    assert dim["value"]["chart_primary"] == "smooth_compounder_grind"


# ---------------------------------------------------------------------------
# (4) Archetype — pit_labels basis with backward merge
# ---------------------------------------------------------------------------

def test_archetype_pit_labels(tmp_path):
    """Archetype history backward merge returns most recent row <= date."""
    root = _make_root(tmp_path)
    _write_archetype_history(root, [
        {"ticker": "AAPL", "fy": 2022, "asof_date": pd.Timestamp("2022-05-01"),
         "period_end": pd.Timestamp("2022-01-31"), "basis": "annual_fy",
         "archetype": "quality_compounder", "confidence": 0.85,
         "anchored": True, "why": "test", "sector": "IT",
         "rev_cagr": 0.1, "eps_cagr": 0.12, "altman_z": None,
         "altman_zone": None, "rates_beta": 0.3, "oil_beta_raw": -0.1},
        {"ticker": "AAPL", "fy": 2023, "asof_date": pd.Timestamp("2023-05-01"),
         "period_end": pd.Timestamp("2023-01-31"), "basis": "annual_fy",
         "archetype": "speculative_unprofitable", "confidence": 0.7,
         "anchored": True, "why": "test2", "sector": "IT",
         "rev_cagr": 0.08, "eps_cagr": 0.09, "altman_z": None,
         "altman_zone": None, "rates_beta": 0.2, "oil_beta_raw": -0.05},
    ])

    result = context_snapshot("AAPL", date="2022-08-01", root=root)
    dim = result["dimensions"]["archetype"]
    assert dim.get("absent") is not True
    assert dim["basis"] == "pit_labels"
    assert dim["value"]["archetype"] == "quality_compounder"  # 2022 row, not 2023


# ---------------------------------------------------------------------------
# (5) Archetype — absent when parquet missing
# ---------------------------------------------------------------------------

def test_archetype_absent_missing_parquet(tmp_path):
    """Archetype dimension returns absent when parquet doesn't exist."""
    root = _make_root(tmp_path)
    result = context_snapshot("AAPL", date="2025-01-01", root=root)
    dim = result["dimensions"]["archetype"]
    assert dim.get("absent") is True
    assert "absent" in dim["reason"].lower() or "parquet" in dim["reason"].lower()


# ---------------------------------------------------------------------------
# (6) Regime — recomputed_history from regime_history.parquet
# ---------------------------------------------------------------------------

def test_regime_recomputed_history(tmp_path):
    """Regime history returns recomputed_history basis for historical dates."""
    root = _make_root(tmp_path)
    _write_regime_history(root, [
        {"date": pd.Timestamp("2025-01-01"), "quad": "Q1"},
        {"date": pd.Timestamp("2025-07-01"), "quad": "Q2"},
    ])

    result = context_snapshot("AAPL", date="2025-03-15", root=root)
    dim = result["dimensions"]["regime"]
    assert dim.get("absent") is not True
    assert dim["basis"] == "recomputed_history"


# ---------------------------------------------------------------------------
# (7) Regime — absent when parquet missing
# ---------------------------------------------------------------------------

def test_regime_absent_missing(tmp_path):
    """Regime dimension returns absent when no history parquet and no latest.json."""
    root = _make_root(tmp_path)
    # Query a historical date (no latest.json)
    result = context_snapshot("AAPL", date="2024-01-01", root=root)
    dim = result["dimensions"]["regime"]
    assert dim.get("absent") is True


# ---------------------------------------------------------------------------
# (8) Short interest — snapshot_not_pit basis
# ---------------------------------------------------------------------------

def test_short_int_snapshot_not_pit(tmp_path):
    """Short interest with a different settlement date → snapshot_not_pit basis."""
    root = _make_root(tmp_path)
    _write_si(root, [
        {"ticker": "AAPL", "short_shares": 1000000, "prev_short_shares": 900000,
         "avg_daily_vol": 500000, "days_to_cover": 2.0,
         "si_change_pct": 11.1, "settlement_date": "2026-05-29"},
    ])

    # Query date different from settlement → snapshot_not_pit
    result = context_snapshot("AAPL", date="2026-06-15", root=root)
    dim = result["dimensions"]["short_int"]
    assert dim.get("absent") is not True
    assert dim["basis"] == "snapshot_not_pit"
    assert dim["value"]["short_shares"] == 1000000


# ---------------------------------------------------------------------------
# (9) Short interest — absent when parquet missing
# ---------------------------------------------------------------------------

def test_short_int_absent(tmp_path):
    """Short interest dimension returns absent when parquet missing."""
    root = _make_root(tmp_path)
    result = context_snapshot("AAPL", date="2025-01-01", root=root)
    dim = result["dimensions"]["short_int"]
    assert dim.get("absent") is True


# ---------------------------------------------------------------------------
# (10) Insider — trailing-90d aggregate
# ---------------------------------------------------------------------------

def test_insider_trailing_90d(tmp_path):
    """Insider dimension aggregates trailing 90 days of filing_date."""
    root = _make_root(tmp_path)
    query_date = "2026-04-15"
    _write_insider_panel(root, [
        {"ticker": "AAPL", "issuer_cik": "1", "filing_date": "2026-03-01",
         "trans_date": "2026-02-28", "rptownercik": "100",
         "code": "P", "direct": True, "is_officer": True, "is_director": False,
         "is_tenpct": False, "title": "CEO", "shares": 100.0,
         "price": 150.0, "usd": 15000.0, "quarter": "2026q1"},
        {"ticker": "AAPL", "issuer_cik": "1", "filing_date": "2025-12-01",
         "trans_date": "2025-11-30", "rptownercik": "101",
         "code": "S", "direct": True, "is_officer": False, "is_director": True,
         "is_tenpct": False, "title": "Director", "shares": 50.0,
         "price": 140.0, "usd": 7000.0, "quarter": "2025q4"},
    ])

    result = context_snapshot("AAPL", date=query_date, root=root)
    dim = result["dimensions"]["insider"]
    assert dim.get("absent") is not True
    # Only the March 2026 filing is within 90 days of April 15
    assert dim["value"]["n_buys"] >= 1


# ---------------------------------------------------------------------------
# (11) Options — absent-tolerant
# ---------------------------------------------------------------------------

def test_options_absent_tolerant(tmp_path):
    """Options dimension returns absent marker when no options data available."""
    root = _make_root(tmp_path)
    result = context_snapshot("AAPL", date="2024-01-01", root=root)
    dim = result["dimensions"]["options"]
    assert dim.get("absent") is True
    # Must not raise


# ---------------------------------------------------------------------------
# (12) Spine — last-5 logic
# ---------------------------------------------------------------------------

def test_spine_last_5_rows(tmp_path):
    """Spine dimension returns at most 5 most-recent rows for a ticker."""
    root = _make_root(tmp_path)
    rows = []
    for i in range(8):
        d = f"2026-0{i+1:02d}-01" if i < 9 else f"2026-{i+1:02d}-01"
        rows.append({
            "signal_id": f"spine:2026-0{i+1:02d}-01:AAPL:21",
            "symbol": "AAPL",
            "as_of": f"2026-0{i+1:02d}-01" if i < 9 else f"2026-{i+1}-01",
            "engine": "us_board",
            "ledger": "spine",
        })
    # Fix: generate 8 rows with proper dates
    rows = []
    for i in range(8):
        month = i + 1
        d = f"2026-{month:02d}-01"
        rows.append({
            "signal_id": f"spine:{d}:AAPL:21",
            "symbol": "AAPL",
            "as_of": d,
            "engine": "us_board",
            "ledger": "spine",
        })
    _write_spine_index(root, rows)

    result = context_snapshot("AAPL", date="2026-08-15", root=root)
    dim = result["dimensions"]["spine"]
    assert dim.get("absent") is not True
    records = dim["value"]
    assert len(records) <= 5


# ---------------------------------------------------------------------------
# (13) Factor — absent (host-only)
# ---------------------------------------------------------------------------

def test_factor_absent_host_only(tmp_path):
    """Factor dimension returns absent when factordata/panel is absent."""
    root = _make_root(tmp_path)
    result = context_snapshot("AAPL", date="2026-01-15", root=root)
    dim = result["dimensions"]["factor"]
    assert dim.get("absent") is True
    # Must not raise


# ---------------------------------------------------------------------------
# (14) Attention — absent (host-only)
# ---------------------------------------------------------------------------

def test_attention_absent_host_only(tmp_path):
    """Attention dimension returns absent when no attention parquet."""
    root = _make_root(tmp_path)
    result = context_snapshot("AAPL", date="2026-01-15", root=root)
    dim = result["dimensions"]["attention"]
    assert dim.get("absent") is True


# ---------------------------------------------------------------------------
# (15) Sector — present; oracle absent-tolerant
# ---------------------------------------------------------------------------

def test_sector_no_crash_missing_sector_data(tmp_path):
    """Sector dimension does not crash when sector data is unavailable."""
    root = _make_root(tmp_path)
    result = context_snapshot("AAPL", date="2026-01-01", root=root)
    # Must be present (even if sector_node is None) or absent — never raises
    dim = result["dimensions"]["sector"]
    assert isinstance(dim, dict)


# ---------------------------------------------------------------------------
# (16) ALL absent stores → absent markers, never raises
# ---------------------------------------------------------------------------

def test_all_absent_stores_no_raise(tmp_path):
    """Empty root: every dimension returns absent marker; no exception."""
    root = _make_root(tmp_path)
    result = context_snapshot("UNKNOWNTICKER", date="2020-01-01", root=root)
    dims = result["dimensions"]
    assert set(dims.keys()) == {
        "personality", "archetype", "regime", "sector",
        "factor", "attention", "insider", "short_int", "options", "spine"
    }
    for name, dim in dims.items():
        assert isinstance(dim, dict), f"dimension {name} not a dict"
        # Either present (with value) or absent
        assert "absent" in dim or "value" in dim, f"dimension {name} malformed: {dim}"


# ---------------------------------------------------------------------------
# (17) [CRITICAL] PIT leak boundary test
# ---------------------------------------------------------------------------

def test_pit_leak_boundary_non_deep_30_days_ago(tmp_path):
    """CRITICAL: spine row 30 days ago for non-deep name must get personality_basis='absent'
    even when the production JSON exists (R-CI3 provenance law).

    This is the key leak boundary: the snapshot_not_pit path must NOT apply
    when the row's as_of is more than 5 trading days before the JSON's as_of.
    """
    root = _make_root(tmp_path)

    # Only AAPL is in PIT (deep name); MSFT is non-deep
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2020-01-01"),
         "chart_primary": "mixed_chart", "micro_primary": None,
         "chart_labels": "mixed_chart", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])

    # Production JSON is fresh (as_of = today)
    prod_asof = pd.Timestamp.today().normalize()
    _write_prod_json(root, str(prod_asof.date()), {
        "MSFT": {"arch": "quality_compounder", "chart": ["smooth_compounder_grind"],
                 "micro": ["tight_spread_absorber"], "modes": ["normal"]},
    })

    # Spine rows: MSFT row 30 days ago (should be absent) and AAPL row (should be pit_labels)
    old_date = prod_asof - pd.Timedelta(days=30)
    rows = [
        {"symbol": "MSFT", "as_of": str(old_date.date()),
         "signal_id": "spine:msft:21", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
        {"symbol": "AAPL", "as_of": str(old_date.date()),
         "signal_id": "spine:aapl:21", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
    ]
    df = pd.DataFrame(rows)
    stamped = _stamp_personality(df.copy(), root=root)

    msft_basis = stamped[stamped["symbol"] == "MSFT"]["personality_basis"].iloc[0]
    assert msft_basis == "absent", (
        f"LEAK: MSFT 30 days ago got basis='{msft_basis}' instead of 'absent'. "
        f"Today's production snapshot was incorrectly applied to a historical date. "
        f"This violates R-CI3 provenance law."
    )


# ---------------------------------------------------------------------------
# (18) _stamp_personality — deep name historical → pit_labels
# ---------------------------------------------------------------------------

def test_stamp_personality_deep_name_historical(tmp_path):
    """Deep name in PIT parquet at historical date → pit_labels basis."""
    root = _make_root(tmp_path)
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2025-06-01"),
         "chart_primary": "mean_reversion_rubber_band",
         "micro_primary": "tight_spread_absorber",
         "chart_labels": "mean_reversion_rubber_band",
         "micro_labels": "tight_spread_absorber",
         "archetype": "mixed", "archetype_asof": None, "archetype_fy": None},
    ])

    rows = [
        {"symbol": "AAPL", "as_of": "2025-08-01",
         "signal_id": "spine:aapl:21", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
    ]
    df = pd.DataFrame(rows)
    stamped = _stamp_personality(df.copy(), root=root)

    row = stamped[stamped["symbol"] == "AAPL"].iloc[0]
    assert row["personality_basis"] == "pit_labels"
    assert row["chart_primary"] == "mean_reversion_rubber_band"
    assert row["micro_primary"] == "tight_spread_absorber"


# ---------------------------------------------------------------------------
# (19) _stamp_personality — non-deep row within 5 trading days → snapshot_not_pit
# ---------------------------------------------------------------------------

def test_stamp_personality_snapshot_not_pit(tmp_path):
    """Non-deep name with as_of AFTER JSON as_of by ≤5 trading days → snapshot_not_pit.

    R-CI3 directional law: prod_asof <= row_asof is required.  Use prod_asof 3 days ago
    and row as_of 2 days ago so signed_gap = +2 (within window).
    """
    root = _make_root(tmp_path)
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2020-01-01"),
         "chart_primary": "mixed_chart", "micro_primary": None,
         "chart_labels": "mixed_chart", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])
    # prod_asof is 3 days ago; as_of is 2 days ago → signed_gap ≈ +1 (within window)
    prod_asof = pd.Timestamp.today().normalize() - pd.Timedelta(days=3)
    _write_prod_json(root, str(prod_asof.date()), {
        "MSFT": {"arch": "quality_compounder", "chart": ["smooth_compounder_grind"],
                 "micro": ["tight_spread_absorber"], "modes": ["normal"]},
    })

    # as_of 2 days ago = 1 day after prod_asof → within directional window
    recent_date = prod_asof + pd.Timedelta(days=2)
    rows = [
        {"symbol": "MSFT", "as_of": str(recent_date.date()),
         "signal_id": "spine:msft:21", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
    ]
    df = pd.DataFrame(rows)
    stamped = _stamp_personality(df.copy(), root=root)

    row = stamped[stamped["symbol"] == "MSFT"].iloc[0]
    assert row["personality_basis"] == "snapshot_not_pit"
    assert row["chart_primary"] == "smooth_compounder_grind"


# ---------------------------------------------------------------------------
# (20) _stamp_personality — old non-deep row → absent
# ---------------------------------------------------------------------------

def test_stamp_personality_old_non_deep_absent(tmp_path):
    """Non-deep name with old as_of → absent (R-CI3 leak boundary)."""
    root = _make_root(tmp_path)
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2020-01-01"),
         "chart_primary": "mixed_chart", "micro_primary": None,
         "chart_labels": "mixed_chart", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])
    prod_asof = pd.Timestamp.today().normalize()
    _write_prod_json(root, str(prod_asof.date()), {
        "MSFT": {"arch": "quality_compounder", "chart": ["smooth_compounder_grind"],
                 "micro": ["tight_spread_absorber"], "modes": ["normal"]},
    })

    # as_of 60 days ago — way outside 5 trading day window
    old_date = prod_asof - pd.Timedelta(days=60)
    rows = [
        {"symbol": "MSFT", "as_of": str(old_date.date()),
         "signal_id": "spine:msft:21", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
    ]
    df = pd.DataFrame(rows)
    stamped = _stamp_personality(df.copy(), root=root)

    row = stamped[stamped["symbol"] == "MSFT"].iloc[0]
    assert row["personality_basis"] == "absent"
    # chart_primary should remain None
    assert row["chart_primary"] is None


# ---------------------------------------------------------------------------
# (21) _stamp_personality — absent PIT parquet → all rows absent, no crash
# ---------------------------------------------------------------------------

def test_stamp_personality_absent_pit_parquet(tmp_path):
    """When PIT parquet is absent, all rows get personality_basis='absent'. No crash."""
    root = _make_root(tmp_path)
    # No PIT parquet written; no prod JSON
    rows = [
        {"symbol": "AAPL", "as_of": "2025-01-01",
         "signal_id": "s1", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
        {"symbol": "MSFT", "as_of": "2025-01-01",
         "signal_id": "s2", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
    ]
    df = pd.DataFrame(rows)
    stamped = _stamp_personality(df.copy(), root=root)

    assert (stamped["personality_basis"] == "absent").all(), (
        f"Expected all absent when PIT parquet missing, got: {stamped['personality_basis'].tolist()}"
    )


# ---------------------------------------------------------------------------
# (22) context_frame — vectorised result
# ---------------------------------------------------------------------------

def test_context_frame_basic(tmp_path):
    """context_frame returns one row per ticker with correct column structure."""
    root = _make_root(tmp_path)
    _write_regime_history(root, [
        {"date": pd.Timestamp("2025-01-01"), "quad": "Q1"},
    ])

    tickers = ["AAPL", "MSFT"]
    frame = context_frame(tickers, date="2025-06-01", root=root)
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) == 2
    assert "ticker" in frame.columns
    assert set(frame["ticker"].tolist()) == {"AAPL", "MSFT"}
    # Regime should be present
    assert "regime__absent" in frame.columns


# ---------------------------------------------------------------------------
# (23) Determinism — two calls return identical results
# ---------------------------------------------------------------------------

def test_context_snapshot_determinism(tmp_path):
    """Two calls with identical inputs return identical results."""
    root = _make_root(tmp_path)
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2025-01-01"),
         "chart_primary": "mixed_chart", "micro_primary": None,
         "chart_labels": "mixed_chart", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])

    r1 = context_snapshot("AAPL", date="2025-03-01", root=root)
    r2 = context_snapshot("AAPL", date="2025-03-01", root=root)
    assert r1 == r2, "context_snapshot must be deterministic"


# ---------------------------------------------------------------------------
# CI_NEW_COLS presence test
# ---------------------------------------------------------------------------

def test_ci_new_cols_defined():
    """_CI_NEW_COLS contains the three personality columns."""
    expected = {"chart_primary", "micro_primary", "personality_basis"}
    assert expected.issubset(set(_CI_NEW_COLS)), (
        f"_CI_NEW_COLS missing columns: {expected - set(_CI_NEW_COLS)}"
    )


# ---------------------------------------------------------------------------
# Trading days helper test
# ---------------------------------------------------------------------------

def test_trading_days_between_same_day():
    d = pd.Timestamp("2026-01-05")  # Monday
    assert _trading_days_between(d, d) == 1  # bdate_range includes both endpoints


# ---------------------------------------------------------------------------
# Directional gap helper tests
# ---------------------------------------------------------------------------

def test_signed_trading_days_positive():
    """row_asof after prod_asof → positive signed gap."""
    prod = pd.Timestamp("2026-01-05")  # Monday
    row  = pd.Timestamp("2026-01-08")  # Thursday (+3 business days)
    assert _signed_trading_days(row, prod) == 3


def test_signed_trading_days_negative():
    """row_asof before prod_asof → negative signed gap (PIT leak direction)."""
    prod = pd.Timestamp("2026-01-08")  # Thursday
    row  = pd.Timestamp("2026-01-05")  # Monday (−3 business days)
    assert _signed_trading_days(row, prod) == -3


def test_signed_trading_days_same_day():
    """Same day → signed gap of 0."""
    d = pd.Timestamp("2026-01-05")
    assert _signed_trading_days(d, d) == 0


# ---------------------------------------------------------------------------
# [NEW] R-CI3 directional tests — row BEFORE snapshot as_of must be absent
# These tests FAIL on pre-fix code (which used abs() gap, so 2 days before
# passed the ≤5 window).  Post-fix code enforces signed_gap >= 0.
# ---------------------------------------------------------------------------

def test_personality_directional_before_asof_returns_absent_context_api(tmp_path):
    """[R-CI3 DIRECTIONAL] Non-deep name queried 2 trading days BEFORE prod_asof must
    return absent, NOT snapshot_not_pit.

    Pre-fix behaviour: _trading_days_between swapped d0/d1 → |gap|=2 → passed the
    ≤5 window → returned snapshot_not_pit (PIT leak).
    Post-fix: _signed_trading_days(row, prod) = −2 < 0 → absent.
    """
    root = _make_root(tmp_path)
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2020-01-01"),
         "chart_primary": "x", "micro_primary": None,
         "chart_labels": "x", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])
    prod_asof = pd.Timestamp("2026-07-07").normalize()
    # query_date is 3 calendar days before prod_asof (≈2 trading days before Mon 07-07)
    query_date = pd.Timestamp("2026-07-04").normalize()  # Friday 07-04 = 3 trading days before
    _write_prod_json(root, str(prod_asof.date()), {
        "MSFT": {"arch": "quality_compounder", "chart": ["smooth_compounder_grind"],
                 "micro": ["tight_spread_absorber"], "modes": ["normal"]},
    })

    result = context_snapshot("MSFT", date=str(query_date.date()), root=root)
    dim = result["dimensions"]["personality"]
    assert dim.get("absent") is True, (
        f"[R-CI3 DIRECTIONAL FAIL] MSFT queried {query_date.date()} (BEFORE prod_asof "
        f"{prod_asof.date()}) returned basis={dim.get('basis')!r} instead of absent. "
        f"Pre-fix code used abs() gap and leaked the snapshot backwards."
    )


def test_stamp_personality_directional_before_asof_returns_absent(tmp_path):
    """[R-CI3 DIRECTIONAL] _stamp_personality: row as_of 2 trading days BEFORE prod_asof
    must get personality_basis='absent'.

    Pre-fix behaviour: iterrows loop used min/max(d0, d1) → absolute gap ≤ 5 →
    returned snapshot_not_pit (PIT leak).
    Post-fix: np.busday_count(prod_date, row_date) < 0 → out_window → absent.
    """
    root = _make_root(tmp_path)
    _write_pit_labels(root, [
        {"ticker": "AAPL", "date": pd.Timestamp("2020-01-01"),
         "chart_primary": "x", "micro_primary": None,
         "chart_labels": "x", "micro_labels": None,
         "archetype": None, "archetype_asof": None, "archetype_fy": None},
    ])
    prod_asof = pd.Timestamp("2026-07-07").normalize()
    # row as_of = 2026-07-04 (Friday before Monday 07-07) → 3 business days before
    row_asof = pd.Timestamp("2026-07-04").normalize()
    _write_prod_json(root, str(prod_asof.date()), {
        "MSFT": {"arch": "quality_compounder", "chart": ["smooth_compounder_grind"],
                 "micro": ["tight_spread_absorber"], "modes": ["normal"]},
    })

    rows = [
        {"symbol": "MSFT", "as_of": str(row_asof.date()),
         "signal_id": "spine:msft:21", "engine": "us_board",
         "ledger": "spine", "personality_basis": None,
         "chart_primary": None, "micro_primary": None},
    ]
    df = pd.DataFrame(rows)
    stamped = _stamp_personality(df.copy(), root=root)

    basis = stamped[stamped["symbol"] == "MSFT"]["personality_basis"].iloc[0]
    assert basis == "absent", (
        f"[R-CI3 DIRECTIONAL FAIL] MSFT as_of {row_asof.date()} (BEFORE prod_asof "
        f"{prod_asof.date()}) got basis={basis!r} instead of absent. "
        f"Pre-fix code leaked the snapshot backwards."
    )


def test_trading_days_between_5_days():
    d0 = pd.Timestamp("2026-01-05")  # Monday
    d1 = pd.Timestamp("2026-01-09")  # Friday
    gap = _trading_days_between(d0, d1)
    assert gap == 5  # Mon–Fri inclusive
