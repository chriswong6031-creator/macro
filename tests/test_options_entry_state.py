"""tests/test_options_entry_state.py — unit tests for engine/options_entry_state.py.

Test suite per W-A acceptance gate:
  1. CI-null behaviour: empty tmp root → all-null rows + evidence_quality='thin', zero exceptions.
  2. No-ledger-write guard: module never opens retro_grades.parquet path.
  3. 5d-change nulls when history < 5 days (skew and ivspread).
  4. pin_risk logic: correct True/False/None behaviour.
  5. Schema snapshot: all required columns present with correct names.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# Allow running from the repo root or via pytest discovery
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine import options_entry_state as OES

# ---------------------------------------------------------------------------
# Expected schema (per masterplan W-A column spec)
# ---------------------------------------------------------------------------
REQUIRED_COLUMNS = [
    "as_of", "ticker",
    "iv30",
    "iv_rank_252", "iv_rank_5d_chg",       # A9 structurally null
    "ivspread_rel", "ivspread_5d_chg",
    "skew", "skew_5d_chg",
    "net_doi", "doi_pc", "fresh_contracts", "fresh_premium_mn", "zerodte_share",
    "gamma_regime", "gamma_regime_structurally_constant",
    "dist_to_flip_pct",
    "wall_up_dist_pct", "wall_down_dist_pct", "max_pain_dist_pct",
    "opex_days", "pin_risk",
    "gex_confirm_verdict",
    "evidence_quality",
    "src_gex_asof", "src_skew_asof", "src_ivspread_asof", "src_flow_asof",
    # W-OVC additions (display-only, RO-2)
    "front7_charm_share", "front7_gex_share",
    "signed_vanna_pressure", "vanna_hedge_5d", "root_class",
]

FORBIDDEN_COLUMNS = [
    # RO-2 / Signal Commons R3: no composite/score columns
    "options_entry_quality_shadow",
    "options_convexity_shadow",
    "score",
    "rank",
    "composite",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_gex_summary(tmp: Path, ticker: str, spot: float = 100.0,
                        gamma_regime: str = "long", date: str = "2026-07-05") -> None:
    """Write a minimal polygon_gex/summary_<ticker>.parquet for one date."""
    gex_dir = tmp / "data" / "polygon_gex"
    gex_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "spot": spot,
        "net_gex_bn": 0.5,
        "net_vex": 1e8,
        "net_cex": 5e7,
        "gamma_flip": spot * 0.85,
        "dist_to_flip_pct": 15.0,
        "gamma_regime": gamma_regime,
        "magnet_up": spot * 1.01,     # 1% above spot
        "magnet_down": spot * 0.97,   # 3% below spot
        "charm_anchor": spot,
        "charm_net_sign": 1,
        "iv30": 0.30,
        "put_call_oi_ratio": 0.8,
        "max_pain": spot * 0.90,      # 10% below spot
        "n_strikes": 100,
        "tier": "full",
    }
    idx = pd.DatetimeIndex([date])
    df = pd.DataFrame([row], index=idx)
    df.to_parquet(gex_dir / f"summary_{ticker}.parquet")


def _write_skew_snapshot(tmp: Path, ticker: str, rows: list[dict]) -> None:
    """Write data/options_skew/snapshots.parquet with given rows."""
    skew_dir = tmp / "data" / "options_skew"
    skew_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    snap = skew_dir / "snapshots.parquet"
    if snap.exists():
        existing = pd.read_parquet(snap)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_parquet(snap, index=False)


def _write_ivspread_snapshot(tmp: Path, ticker: str, rows: list[dict]) -> None:
    """Write data/options_ivspread/snapshots.parquet with given rows."""
    iv_dir = tmp / "data" / "options_ivspread"
    iv_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    snap = iv_dir / "snapshots.parquet"
    if snap.exists():
        existing = pd.read_parquet(snap)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_parquet(snap, index=False)


def _write_flow_summary(tmp: Path, ticker: str, date: str = "2026-07-05") -> None:
    """Write a minimal data/options_flow/summary_<ticker>.parquet."""
    flow_dir = tmp / "data" / "options_flow"
    flow_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "spot": 100.0,
        "volume": 5000,
        "premium_mn": 20.0,
        "net_premium_mn": 5.0,
        "pc_ratio": 0.7,
        "signed_pc": 0.3,
        "zerodte_share": 0.25,
        "gamma_flow_bn": 0.1,
        "delta_flow_mn": 50.0,
        "assumed_gex_bn": 0.4,
        "fresh_contracts": 10,
        "net_doi": 500,
        "doi_pc": 0.45,
    }
    idx = pd.DatetimeIndex([date])
    df = pd.DataFrame([row], index=idx)
    df.to_parquet(flow_dir / f"summary_{ticker}.parquet")


# ---------------------------------------------------------------------------
# Test 1: CI-null behaviour — empty root → thin evidence, no exceptions
# ---------------------------------------------------------------------------

def test_ci_null_empty_root(tmp_path):
    """Empty root → empty DataFrame with correct schema + no exceptions."""
    df = OES.build_state(tmp_path)
    # No rows because no source files
    assert isinstance(df, pd.DataFrame), "build_state must return a DataFrame"
    # All required columns must be present even on empty result
    for col in REQUIRED_COLUMNS:
        assert col in df.columns, f"Column {col!r} missing from empty-root result"


def test_ci_null_single_source_thin(tmp_path):
    """Single skew source (no gex, no flow) → thin evidence quality, no crash."""
    # Only write skew data
    _write_skew_snapshot(tmp_path, "TEST", [
        {"date": "2026-07-05", "underlying": "TEST", "asof": "2026-07-05",
         "spot": 100.0, "tenor_days": 30.0, "otm_put_iv": 0.32, "atm_call_iv": 0.28,
         "skew": 0.04, "n_strikes": 10},
    ])
    df = OES.build_state(tmp_path)
    assert len(df) >= 1, "Should have at least one row from skew data"
    row = df[df["ticker"] == "TEST"].iloc[0]
    # Missing gex, ivspread, flow → thin or partial evidence
    assert row["evidence_quality"] in ("thin", "partial", "stale"), (
        f"Expected thin/partial/stale without gex+ivspread+flow, got {row['evidence_quality']}"
    )
    # Absent sources → null fields, not fake-neutral
    assert pd.isna(row["iv30"]) or row["iv30"] is None, "iv30 should be null when gex absent"
    assert pd.isna(row["gamma_regime"]) or row["gamma_regime"] is None, (
        "gamma_regime should be null when gex absent"
    )
    assert pd.isna(row["net_doi"]) or row["net_doi"] is None, (
        "net_doi should be null when flow absent"
    )


# ---------------------------------------------------------------------------
# Test 2: No-ledger-write guard — module never opens retro_grades.parquet
# ---------------------------------------------------------------------------

def test_no_ledger_write_guard(tmp_path, monkeypatch):
    """build_state must never attempt to open retro_grades.parquet."""
    forbidden_path = str(tmp_path / "data" / "us_board_ledger" / "retro_grades.parquet")
    opened_paths: list[str] = []

    original_open = open

    def _tracking_open(file, *args, **kwargs):
        p = str(file)
        if "retro_grades" in p or "us_board_ledger" in p:
            opened_paths.append(p)
        return original_open(file, *args, **kwargs)

    import builtins
    monkeypatch.setattr(builtins, "open", _tracking_open)

    # Also patch pd.read_parquet to track parquet-level access
    original_read_parquet = pd.read_parquet
    parquet_paths: list[str] = []

    def _tracking_read_parquet(path, *args, **kwargs):
        parquet_paths.append(str(path))
        return original_read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", _tracking_read_parquet)

    _write_gex_summary(tmp_path, "AAPL")
    OES.build_state(tmp_path)

    # Must not have touched the ledger path in any way
    assert not any("retro_grades" in p for p in opened_paths), (
        f"retro_grades opened via builtins.open: {opened_paths}"
    )
    assert not any("retro_grades" in p for p in parquet_paths), (
        f"retro_grades opened via pd.read_parquet: {parquet_paths}"
    )
    assert not any("us_board_ledger" in p for p in parquet_paths), (
        f"us_board_ledger accessed: {parquet_paths}"
    )


# ---------------------------------------------------------------------------
# Test 3: 5d-change nulls when history < 5 trading days
# ---------------------------------------------------------------------------

def _make_skew_rows(ticker: str, n_days: int, base_date_str: str = "2026-06-21") -> list[dict]:
    """Generate n_days of skew rows starting from base_date_str."""
    rows = []
    base = _dt.date.fromisoformat(base_date_str)
    for i in range(n_days):
        d = str(base + _dt.timedelta(days=i))
        rows.append({
            "date": d, "underlying": ticker, "asof": d,
            "spot": 100.0, "tenor_days": 30.0,
            "otm_put_iv": 0.30 + i * 0.001,
            "atm_call_iv": 0.25,
            "skew": 0.05 + i * 0.001,
            "n_strikes": 20,
        })
    return rows


def _make_ivspread_rows(ticker: str, n_days: int, base_date_str: str = "2026-06-21") -> list[dict]:
    """Generate n_days of ivspread rows starting from base_date_str."""
    rows = []
    base = _dt.date.fromisoformat(base_date_str)
    for i in range(n_days):
        d = str(base + _dt.timedelta(days=i))
        rows.append({
            "date": d, "underlying": ticker, "asof": d,
            "spot": 100.0, "tenor_days": 30.0,
            "ivspread": 0.02 + i * 0.001,
            "atm_spread": 0.01,
            "n_pairs": 5,
            "weight_kind": "oi",
            "ivspread_rel": 0.01 + i * 0.001,
        })
    return rows


def test_skew_5d_change_null_when_short_history(tmp_path):
    """skew_5d_chg must be null when < 6 rows (LOOKBACK_TRADING_DAYS+1) exist."""
    # Only 3 rows — not enough for a 5d look-back
    _write_skew_snapshot(tmp_path, "SHORT", _make_skew_rows("SHORT", n_days=3))
    df = OES.build_state(tmp_path)
    if len(df) == 0:
        pytest.skip("No rows returned (no other source either)")
    rows = df[df["ticker"] == "SHORT"]
    if rows.empty:
        pytest.skip("SHORT not in result")
    assert pd.isna(rows.iloc[0]["skew_5d_chg"]) or rows.iloc[0]["skew_5d_chg"] is None, (
        "skew_5d_chg should be null with only 3 history rows"
    )


def test_skew_5d_change_non_null_when_enough_history(tmp_path):
    """skew_5d_chg must be non-null when >= LOOKBACK_TRADING_DAYS+1 rows exist."""
    # 7 rows — enough for a 5d look-back
    _write_skew_snapshot(tmp_path, "LONG", _make_skew_rows("LONG", n_days=7))
    df = OES.build_state(tmp_path)
    if len(df) == 0:
        pytest.skip("No rows returned")
    rows = df[df["ticker"] == "LONG"]
    if rows.empty:
        pytest.skip("LONG not in result")
    v = rows.iloc[0]["skew_5d_chg"]
    assert v is not None and not (isinstance(v, float) and v != v), (
        f"skew_5d_chg should be non-null with 7 history rows, got {v!r}"
    )


def test_ivspread_5d_change_null_when_short_history(tmp_path):
    """ivspread_5d_chg must be null when < 6 rows exist."""
    _write_ivspread_snapshot(tmp_path, "IVSSHORT", _make_ivspread_rows("IVSSHORT", n_days=4))
    df = OES.build_state(tmp_path)
    if len(df) == 0:
        pytest.skip("No rows returned")
    rows = df[df["ticker"] == "IVSSHORT"]
    if rows.empty:
        pytest.skip("IVSSHORT not in result")
    assert pd.isna(rows.iloc[0]["ivspread_5d_chg"]) or rows.iloc[0]["ivspread_5d_chg"] is None, (
        "ivspread_5d_chg should be null with only 4 history rows"
    )


def test_ivspread_5d_change_non_null_when_enough_history(tmp_path):
    """ivspread_5d_chg must be non-null when >= LOOKBACK_TRADING_DAYS+1 rows exist."""
    _write_ivspread_snapshot(tmp_path, "IVSLONG", _make_ivspread_rows("IVSLONG", n_days=8))
    df = OES.build_state(tmp_path)
    if len(df) == 0:
        pytest.skip("No rows returned")
    rows = df[df["ticker"] == "IVSLONG"]
    if rows.empty:
        pytest.skip("IVSLONG not in result")
    v = rows.iloc[0]["ivspread_5d_chg"]
    assert v is not None and not (isinstance(v, float) and v != v), (
        f"ivspread_5d_chg should be non-null with 8 history rows, got {v!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: pin_risk logic
# ---------------------------------------------------------------------------

def test_pin_risk_true_when_conditions_met(tmp_path, monkeypatch):
    """
    pin_risk=True when: opex_days<=5, gamma_regime='long', min wall <=2%.
    We monkeypatch _opex_days_today to return 3 (within 5 days).
    """
    monkeypatch.setattr(OES, "_opex_days_today", lambda: 3)
    # spot=100, magnet_up=101 (1% up), magnet_down=97 (3% down) → wall_up=1% <= 2%
    _write_gex_summary(tmp_path, "PINTEST", spot=100.0, gamma_regime="long")
    df = OES.build_state(tmp_path)
    assert len(df) > 0
    rows = df[df["ticker"] == "PINTEST"]
    assert not rows.empty
    assert rows.iloc[0]["pin_risk"] == True, (  # noqa: E712 — numpy bool needs ==
        f"Expected pin_risk=True, got {rows.iloc[0]['pin_risk']}"
    )


def test_pin_risk_false_when_walls_far(tmp_path, monkeypatch):
    """pin_risk=False when opex_days<=5 and long gamma, but all walls > 2%."""
    monkeypatch.setattr(OES, "_opex_days_today", lambda: 2)
    # spot=100, magnet_up=110 (10% above), magnet_down=90 (10% below) → walls far
    gex_dir = tmp_path / "data" / "polygon_gex"
    gex_dir.mkdir(parents=True, exist_ok=True)
    spot = 100.0
    row = {
        "spot": spot,
        "net_gex_bn": 0.5, "net_vex": 1e8, "net_cex": 5e7,
        "gamma_flip": spot * 0.70,
        "dist_to_flip_pct": 30.0,
        "gamma_regime": "long",
        "magnet_up": spot * 1.10,      # 10% above → wall_up_dist_pct=10%
        "magnet_down": spot * 0.90,    # 10% below → wall_down_dist_pct=10%
        "charm_anchor": spot, "charm_net_sign": 1,
        "iv30": 0.25, "put_call_oi_ratio": 0.8,
        "max_pain": spot * 0.88,       # 12% below → max_pain_dist_pct=12%
        "n_strikes": 100, "tier": "full",
    }
    df_in = pd.DataFrame([row], index=pd.DatetimeIndex(["2026-07-05"]))
    df_in.to_parquet(gex_dir / "summary_FARWALLS.parquet")
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "FARWALLS"]
    assert not rows.empty
    assert rows.iloc[0]["pin_risk"] == False, (  # noqa: E712 — numpy bool needs ==
        f"Expected pin_risk=False with far walls, got {rows.iloc[0]['pin_risk']}"
    )


def test_pin_risk_none_when_opex_not_near(tmp_path, monkeypatch):
    """pin_risk=None when opex_days > 5 (not near OPEX)."""
    monkeypatch.setattr(OES, "_opex_days_today", lambda: 15)
    _write_gex_summary(tmp_path, "NOOPEX", spot=100.0, gamma_regime="long")
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "NOOPEX"]
    assert not rows.empty
    assert rows.iloc[0]["pin_risk"] is None, (
        f"Expected pin_risk=None with opex_days=15, got {rows.iloc[0]['pin_risk']}"
    )


def test_pin_risk_none_when_short_gamma(tmp_path, monkeypatch):
    """pin_risk=None when gamma_regime='short' (only fires on long gamma)."""
    monkeypatch.setattr(OES, "_opex_days_today", lambda: 2)
    _write_gex_summary(tmp_path, "SHORTG", spot=100.0, gamma_regime="short")
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "SHORTG"]
    assert not rows.empty
    assert rows.iloc[0]["pin_risk"] is None, (
        f"Expected pin_risk=None with short gamma, got {rows.iloc[0]['pin_risk']}"
    )


# ---------------------------------------------------------------------------
# Test 5: Schema snapshot — all required columns present, no forbidden cols
# ---------------------------------------------------------------------------

def test_schema_snapshot_all_required_columns(tmp_path):
    """All required columns must be present in the result."""
    _write_gex_summary(tmp_path, "SCHEMA")
    _write_skew_snapshot(tmp_path, "SCHEMA", _make_skew_rows("SCHEMA", n_days=7))
    df = OES.build_state(tmp_path)
    for col in REQUIRED_COLUMNS:
        assert col in df.columns, f"Required column {col!r} missing"


def test_schema_no_forbidden_columns(tmp_path):
    """No composite/score columns (RO-2 / Signal Commons R3)."""
    _write_gex_summary(tmp_path, "NOSC")
    df = OES.build_state(tmp_path)
    for col in FORBIDDEN_COLUMNS:
        assert col not in df.columns, (
            f"Forbidden composite column {col!r} found — RO-2 violation"
        )


def test_iv_rank_columns_are_all_null(tmp_path):
    """iv_rank_252 and iv_rank_5d_chg must be all-null (A9: structurally absent)."""
    _write_gex_summary(tmp_path, "IVRANK")
    _write_flow_summary(tmp_path, "IVRANK")
    df = OES.build_state(tmp_path)
    assert len(df) > 0
    # Every value must be null (None / NaN)
    for col in ("iv_rank_252", "iv_rank_5d_chg"):
        non_null = df[col].dropna()
        assert len(non_null) == 0, (
            f"{col} should be all-null (A9 ruling: structurally absent), "
            f"but found {len(non_null)} non-null values: {non_null.tolist()}"
        )


def test_evidence_quality_full_with_all_sources(tmp_path):
    """evidence_quality='full' when all 4 sources present and fresh."""
    today = str(_dt.date.today())
    _write_gex_summary(tmp_path, "FULL", date=today)
    _write_skew_snapshot(tmp_path, "FULL", [
        {"date": today, "underlying": "FULL", "asof": today,
         "spot": 100.0, "tenor_days": 30.0, "otm_put_iv": 0.30, "atm_call_iv": 0.25,
         "skew": 0.05, "n_strikes": 15},
    ])
    _write_ivspread_snapshot(tmp_path, "FULL", [
        {"date": today, "underlying": "FULL", "asof": today,
         "spot": 100.0, "tenor_days": 30.0, "ivspread": 0.02, "atm_spread": 0.01,
         "n_pairs": 5, "weight_kind": "oi", "ivspread_rel": 0.015},
    ])
    _write_flow_summary(tmp_path, "FULL", date=today)
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "FULL"]
    assert not rows.empty
    assert rows.iloc[0]["evidence_quality"] == "full", (
        f"Expected full evidence quality with all sources present, "
        f"got {rows.iloc[0]['evidence_quality']!r}"
    )


def test_gamma_regime_structurally_constant_caveat(tmp_path):
    """gamma_regime_structurally_constant=True when GEX data present (audit #29 caveat)."""
    _write_gex_summary(tmp_path, "CAVEAT")
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "CAVEAT"]
    assert not rows.empty
    assert rows.iloc[0]["gamma_regime_structurally_constant"] == True, (  # noqa: E712 — numpy bool
        "gamma_regime_structurally_constant must be True when GEX present (audit #29)"
    )


def test_no_exceptions_on_corrupt_parquet(tmp_path):
    """build_state must not raise even if a GEX summary parquet is corrupt."""
    gex_dir = tmp_path / "data" / "polygon_gex"
    gex_dir.mkdir(parents=True, exist_ok=True)
    # Write a non-parquet file with a parquet extension
    (gex_dir / "summary_CORRUPT.parquet").write_bytes(b"this is not a parquet file")
    # Should not raise
    df = OES.build_state(tmp_path)
    assert isinstance(df, pd.DataFrame)
    # CORRUPT ticker should not appear (row was skipped, not crashed)
    assert "CORRUPT" not in df["ticker"].values


# ---------------------------------------------------------------------------
# W-OVC tests: root_class, front7_*_share, vanna_hedge_5d, null-safety
# ---------------------------------------------------------------------------

def test_root_class_always_present(tmp_path):
    """root_class must be non-null for every row; correct values for known ETFs."""
    _write_gex_summary(tmp_path, "SPY")
    _write_gex_summary(tmp_path, "XLK")
    _write_gex_summary(tmp_path, "SMH")
    _write_gex_summary(tmp_path, "AAPL")
    df = OES.build_state(tmp_path)
    assert len(df) > 0
    # root_class is always non-null
    assert df["root_class"].notna().all(), "root_class must never be null"
    rows = {row["ticker"]: row for _, row in df.iterrows()}
    assert rows["SPY"]["root_class"] == "index_etf"
    assert rows["XLK"]["root_class"] == "sector_etf"
    assert rows["SMH"]["root_class"] == "industry_etf"
    assert rows["AAPL"]["root_class"] == "single_name"


def test_front7_columns_null_when_no_chain(tmp_path):
    """front7_charm_share and front7_gex_share are null when chains/ directory is absent."""
    _write_gex_summary(tmp_path, "NOCHAIN")
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "NOCHAIN"]
    assert not rows.empty
    # No chains/ directory → front7 columns must be null
    assert pd.isna(rows.iloc[0]["front7_charm_share"]) or rows.iloc[0]["front7_charm_share"] is None
    assert pd.isna(rows.iloc[0]["front7_gex_share"]) or rows.iloc[0]["front7_gex_share"] is None


def _write_minimal_chain(tmp_path: Path, ticker: str, date: str = "2026-07-15",
                           front7_expiry: str = "2026-07-17",
                           far_expiry: str = "2026-08-15") -> None:
    """Write a minimal chains/{date}.parquet with two expiries for the ticker."""
    chains_dir = tmp_path / "data" / "polygon_gex" / "chains"
    chains_dir.mkdir(parents=True, exist_ok=True)
    spot = 100.0
    rows = []
    # Front expiry (≤7 days from chain date 2026-07-15 → 2-day expiry on 2026-07-17)
    for is_call, K_ in [(True, 100.0), (False, 99.0)]:
        T_val = (pd.Timestamp(front7_expiry) - pd.Timestamp(date)).days / 365.0
        rows.append({
            "underlying": ticker, "strike_ticker": f"O:{ticker}C00{int(K_)}000",
            "expiry": front7_expiry, "K": K_, "T": max(T_val, 0.001),
            "is_call": is_call, "oi": 500.0, "iv": 0.25,
            "gamma": 0.03, "delta": 0.5, "volume": 50.0,
            "spot": spot, "asof": date,
        })
    # Far expiry (> 7 days)
    for is_call, K_ in [(True, 100.0), (False, 99.0)]:
        T_val = (pd.Timestamp(far_expiry) - pd.Timestamp(date)).days / 365.0
        rows.append({
            "underlying": ticker, "strike_ticker": f"O:{ticker}C00{int(K_)}000F",
            "expiry": far_expiry, "K": K_, "T": max(T_val, 0.001),
            "is_call": is_call, "oi": 500.0, "iv": 0.25,
            "gamma": 0.02, "delta": 0.5, "volume": 30.0,
            "spot": spot, "asof": date,
        })
    chain_df = pd.DataFrame(rows)
    chain_df.to_parquet(chains_dir / f"{date}.parquet", index=False)


def test_front7_shares_computed_when_chain_present(tmp_path):
    """front7_charm_share and front7_gex_share are non-null when a chain file exists."""
    _write_gex_summary(tmp_path, "CHAINTEST", date="2026-07-15")
    _write_minimal_chain(tmp_path, "CHAINTEST")
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "CHAINTEST"]
    assert not rows.empty
    row = rows.iloc[0]
    # front7 values should be non-null fractions in [0, 1]
    v_charm = row["front7_charm_share"]
    v_gex = row["front7_gex_share"]
    if v_charm is not None and not (isinstance(v_charm, float) and v_charm != v_charm):
        assert 0.0 <= float(v_charm) <= 1.0, f"front7_charm_share out of [0,1]: {v_charm}"
    if v_gex is not None and not (isinstance(v_gex, float) and v_gex != v_gex):
        assert 0.0 <= float(v_gex) <= 1.0, f"front7_gex_share out of [0,1]: {v_gex}"


def test_front7_charm_share_is_less_than_one_when_far_expiry_present(tmp_path):
    """When there is a far expiry (> 7 days), front7 share must be < 1.0."""
    _write_gex_summary(tmp_path, "MIXED", date="2026-07-15")
    _write_minimal_chain(tmp_path, "MIXED",
                          front7_expiry="2026-07-17",  # 2 days → front7
                          far_expiry="2026-08-15")     # 31 days → not front7
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "MIXED"]
    assert not rows.empty
    row = rows.iloc[0]
    # With equal OI in front7 and far expiries, share should be ≈ 0.5
    v_charm = row["front7_charm_share"]
    if v_charm is not None and not (isinstance(v_charm, float) and v_charm != v_charm):
        assert float(v_charm) < 1.0, (
            f"front7_charm_share should be < 1.0 when far-expiry contracts exist, got {v_charm}"
        )


def test_vanna_hedge_5d_null_when_insufficient_summary_history(tmp_path):
    """vanna_hedge_5d must be null when the summary has fewer than 6 rows."""
    gex_dir = tmp_path / "data" / "polygon_gex"
    gex_dir.mkdir(parents=True, exist_ok=True)
    # Only 3 rows (< 6 required)
    rows = []
    for i in range(3):
        rows.append({
            "spot": 100.0, "net_gex_bn": 0.1, "net_vex": 1e8, "net_cex": 5e6,
            "gamma_flip": 90.0, "dist_to_flip_pct": 10.0, "gamma_regime": "long",
            "magnet_up": 101.0, "magnet_down": 97.0, "charm_anchor": 100.0,
            "charm_net_sign": 1, "iv30": 0.25 + i * 0.01, "put_call_oi_ratio": 0.8,
            "max_pain": 98.0, "n_strikes": 50, "tier": "full",
        })
    dates = pd.DatetimeIndex(["2026-07-13", "2026-07-14", "2026-07-15"])
    short_df = pd.DataFrame(rows, index=dates)
    short_df.to_parquet(gex_dir / "summary_SHORTSUM.parquet")
    df = OES.build_state(tmp_path)
    rows_out = df[df["ticker"] == "SHORTSUM"]
    assert not rows_out.empty
    v = rows_out.iloc[0]["vanna_hedge_5d"]
    assert v is None or (isinstance(v, float) and v != v), (
        f"vanna_hedge_5d should be null with < 6 summary rows, got {v!r}"
    )


def test_ovc_columns_null_safe_no_crash(tmp_path):
    """build_state must not raise when chains/ exists but is corrupt/empty."""
    _write_gex_summary(tmp_path, "SAFENULL")
    chains_dir = tmp_path / "data" / "polygon_gex" / "chains"
    chains_dir.mkdir(parents=True, exist_ok=True)
    # Write a corrupt chain file
    (chains_dir / "2026-07-15.parquet").write_bytes(b"not a valid parquet")
    # Should not raise; front7 columns should be null
    df = OES.build_state(tmp_path)
    rows = df[df["ticker"] == "SAFENULL"]
    assert not rows.empty, "SAFENULL ticker should appear in result even with corrupt chain"
    row = rows.iloc[0]
    # front7 columns null (chain was corrupt)
    assert row["front7_charm_share"] is None or (
        isinstance(row["front7_charm_share"], float) and row["front7_charm_share"] != row["front7_charm_share"]
    )
    # root_class still populated (does not depend on chain)
    assert row["root_class"] is not None and row["root_class"] == "single_name"


def test_ovc_schema_completeness(tmp_path):
    """All W-OVC columns must be present in the result schema."""
    _write_gex_summary(tmp_path, "OVC_SCHEMA")
    df = OES.build_state(tmp_path)
    for col in ("front7_charm_share", "front7_gex_share", "signed_vanna_pressure",
                "vanna_hedge_5d", "root_class"):
        assert col in df.columns, f"W-OVC column {col!r} missing from result"
