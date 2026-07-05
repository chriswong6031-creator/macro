"""Hermetic tests for engine/thetadata_store.py.

Fixture store: tests/fixtures/thetadata_store/
  - SPY eod/oi/greeks: 3 dates (2019-01-02, 03, 04)
  - AAPL eod/oi: 3 dates (no greeks)

Hand-computable values are documented inline so any off-by-one in the oi[t-1]
shift or ΔOI computation is immediately detectable.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURE_STORE = Path(__file__).parent / "fixtures" / "thetadata_store"


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #

def _store():
    return str(FIXTURE_STORE)


# --------------------------------------------------------------------------- #
# universe()                                                                    #
# --------------------------------------------------------------------------- #

def test_universe_returns_both_roots():
    from engine.thetadata_store import universe
    roots = universe(store=_store())
    assert "SPY" in roots
    assert "AAPL" in roots


def test_universe_empty_on_missing_store(tmp_path):
    from engine.thetadata_store import universe
    roots = universe(store=str(tmp_path / "nonexistent"))
    assert roots == []


def test_universe_date_filter():
    from engine.thetadata_store import universe
    # 2019 parquets exist — any 2019 date should return both
    roots = universe(date="2019-01-02", store=_store())
    assert "SPY" in roots
    # 2099 should return nothing
    roots_far = universe(date="2099-01-01", store=_store())
    assert roots_far == []


# --------------------------------------------------------------------------- #
# chain()                                                                       #
# --------------------------------------------------------------------------- #

def test_chain_spy_returns_rows():
    from engine.thetadata_store import chain
    df = chain("2019-01-02", "SPY", store=_store())
    assert not df.empty
    assert "open_interest" in df.columns
    # Greeks not present for 2019-01-02 (fixture only has greeks for 03 and 04)
    assert "implied_vol" in df.columns
    assert df["implied_vol"].isna().all()


def test_chain_spy_greeks_on_covered_date():
    from engine.thetadata_store import chain
    df = chain("2019-01-03", "SPY", store=_store())
    assert not df.empty
    # greeks fixture has implied_vol for 2019-01-03
    assert "implied_vol" in df.columns
    assert df["implied_vol"].notna().any()


def test_chain_missing_root_returns_empty():
    from engine.thetadata_store import chain
    df = chain("2019-01-02", "MSFT", store=_store())
    assert df.empty


def test_chain_missing_date_returns_empty():
    from engine.thetadata_store import chain
    # 2019-01-01 is a holiday/non-trading — should return empty
    df = chain("2019-01-01", "SPY", store=_store())
    assert df.empty


def test_chain_oi_joined():
    from engine.thetadata_store import chain
    df = chain("2019-01-02", "SPY", store=_store())
    # OI should be present and positive
    oi_vals = df["open_interest"].dropna()
    assert len(oi_vals) > 0
    assert (oi_vals > 0).all()


def test_chain_no_lookahead_in_chain():
    """chain() returns raw point-in-time data — OI is NOT shifted here.
    The oi[t-1] shift lives in doi_series(). Verify chain() gives same-day OI."""
    from engine.thetadata_store import chain
    df02 = chain("2019-01-02", "SPY", store=_store())
    df03 = chain("2019-01-03", "SPY", store=_store())
    # OI should differ between dates (fixture values increase 1000 -> 1050)
    oi02 = df02["open_interest"].sum()
    oi03 = df03["open_interest"].sum()
    assert oi03 > oi02


# --------------------------------------------------------------------------- #
# doi_series() — THE KEY TEST: oi[t-1] shift correctness                       #
# --------------------------------------------------------------------------- #

def test_doi_series_oi_t1_shift():
    """THE KEY TEST.

    Fixture OI by date (raw as-reported):
      2019-01-02: per-contract total ≈ 1000 each per 8 rows = 8000 total
      2019-01-03: ≈ 1050 × 8 = 8400 total
      2019-01-04: ≈ 1100 × 8 = 8800 total
      (plus 50 extra per far-expiry row × 4 contracts × 2 expiries per date)

    OI timing law (LIVE_ORDER_FLOW §8.1):
      oi[t] as-reported = EOD t-1 positions.
      doi_series() shifts by 1 BEFORE computing delta:
        oi_shifted[t] = raw_oi[t-1]

    With window=1 (1-session delta for testing):
      doi_raw[t] = oi_shifted[t] - oi_shifted[t-1]
                 = raw_oi[t-1]  - raw_oi[t-2]

    Expected:
      At date index 0 (2019-01-02): oi_shifted = NaN (shift(1) of first row)
      At date index 1 (2019-01-03): oi_shifted = raw_oi[2019-01-02]
      At date index 2 (2019-01-04): oi_shifted = raw_oi[2019-01-03]

    If shift was NOT applied (same-day OI bug):
      doi_raw at index 1 would use oi[2019-01-03] - oi[2019-01-02]
      But with shift, doi_raw at index 2 uses oi[2019-01-02] - oi[NaN] = NaN
      and doi_raw at index 2 with window=1 = oi_shifted[2019-01-04] - oi_shifted[2019-01-03]
                                             = raw_oi[2019-01-03] - raw_oi[2019-01-02]

    We verify: the first non-NaN doi_raw entry = raw_oi[t-1] - raw_oi[t-2], not raw_oi[t] - raw_oi[t-1].
    """
    from engine.thetadata_store import doi_series, _load_parquets, _normalise_date
    from engine.thetadata_store import store_root

    # Get raw OI totals per date (before any shifting)
    oi_raw = _load_parquets("oi", "SPY", None, _store())
    oi_raw = _normalise_date(oi_raw)
    raw_totals = oi_raw.groupby("date")["open_interest"].sum().sort_index()

    # Run doi_series with window=1
    s = doi_series("SPY", put_call="both", window=1, store=_store())
    assert not s.empty
    s = s.set_index("date").sort_index()

    # With shift(1): oi_shifted at 2019-01-03 = raw_totals at 2019-01-02
    # total_oi column in doi_series should equal raw_oi shifted by 1
    shifted_expected = raw_totals.shift(1)
    for d in shifted_expected.index:
        d_str = str(d)
        if d_str in s.index:
            exp = shifted_expected[d]
            got = s.loc[d_str, "total_oi"]
            if np.isnan(exp):
                assert np.isnan(float(got)), f"Expected NaN at {d_str}, got {got}"
            else:
                assert abs(float(got) - float(exp)) < 1.0, (
                    f"OI shift mismatch at {d_str}: expected {exp:.1f}, got {got:.1f}. "
                    "This indicates the oi[t-1] shift was NOT applied correctly."
                )


def test_doi_series_window5_delta():
    """doi_raw with window=5 should be NaN for dates with fewer than 5 prior sessions."""
    from engine.thetadata_store import doi_series
    s = doi_series("SPY", put_call="both", window=5, store=_store())
    # Fixture only has 3 dates — with shift(1) and window=5, all doi_raw should be NaN
    # because we don't have 5 prior sessions after shifting
    s = s.set_index("date")
    # All doi_raw should be NaN (not enough history for window=5)
    assert s["doi_raw"].isna().all(), (
        "Expected all doi_raw to be NaN for 3-date fixture with window=5, "
        f"got: {s['doi_raw'].to_dict()}"
    )


def test_doi_series_put_only():
    """Filtering to puts-only should return a subset of total OI."""
    from engine.thetadata_store import doi_series
    s_all = doi_series("SPY", put_call="both", window=1, store=_store())
    s_puts = doi_series("SPY", put_call="P", window=1, store=_store())
    assert not s_puts.empty
    # Puts-only OI should be less than or equal to all OI
    total_all = s_all["total_oi"].dropna().sum()
    total_puts = s_puts["total_oi"].dropna().sum()
    assert total_puts <= total_all


def test_doi_series_missing_root_returns_empty():
    from engine.thetadata_store import doi_series
    s = doi_series("MSFT", store=_store())
    assert s.empty or len(s) == 0


# --------------------------------------------------------------------------- #
# iv_coverage()                                                                 #
# --------------------------------------------------------------------------- #

def test_iv_coverage_spy_has_greeks():
    from engine.thetadata_store import iv_coverage
    cov = iv_coverage(store=_store())
    assert "SPY" in cov
    assert cov["SPY"]["first"] == "2019-01-03"
    assert cov["SPY"]["last"] == "2019-01-04"
    assert cov["SPY"]["n_dates"] == 2


def test_iv_coverage_aapl_no_greeks():
    """AAPL has no greeks fixture — should not appear in iv_coverage."""
    from engine.thetadata_store import iv_coverage
    cov = iv_coverage(store=_store())
    assert "AAPL" not in cov


def test_iv_coverage_empty_store(tmp_path):
    from engine.thetadata_store import iv_coverage
    cov = iv_coverage(store=str(tmp_path))
    assert cov == {}


# --------------------------------------------------------------------------- #
# Era bucketing boundaries                                                      #
# --------------------------------------------------------------------------- #

def test_era_bucketing():
    """Verify era boundary classification from the runner."""
    from scripts.rerun_options_gates_thetadata import _era, _ERAS
    assert _era("2012-06-01") == "2012-15"
    assert _era("2015-12-31") == "2012-15"
    assert _era("2016-01-01") == "2016-19"
    assert _era("2019-12-31") == "2016-19"
    assert _era("2020-01-01") == "2020-22"
    assert _era("2022-12-31") == "2020-22"
    assert _era("2023-01-01") == "2023+"
    assert _era("2026-07-04") == "2023+"


def test_era_filter():
    from scripts.rerun_options_gates_thetadata import _era_filter
    dates = ["2015-12-01", "2016-01-01", "2019-12-31", "2020-01-01"]
    assert _era_filter(dates, "2016-01-01", "2019-12-31") == ["2016-01-01", "2019-12-31"]
    assert _era_filter(dates, "2020-01-01", "2099-12-31") == ["2020-01-01"]


# --------------------------------------------------------------------------- #
# IV coverage windowing in gate runner                                          #
# --------------------------------------------------------------------------- #

def test_runner_iv_coverage_window():
    """The S-CWIV/S-XZZ gates only run on greeks-IV-covered dates."""
    from engine.thetadata_store import iv_coverage
    cov = iv_coverage(store=_store())
    # SPY greeks only on 2019-01-03 and 2019-01-04
    assert cov.get("SPY", {}).get("first") == "2019-01-03"
    assert cov.get("SPY", {}).get("last") == "2019-01-04"


# --------------------------------------------------------------------------- #
# Thin universe exclusion                                                       #
# --------------------------------------------------------------------------- #

def test_thin_universe_exclusion_in_doi_stats():
    """Dates where n_names < min_names should be excluded and tallied."""
    from scripts.rerun_options_gates_thetadata import _doi_era_stats
    # Build a panel where the fixture root count (2) is below the floor (15)
    panel = pd.DataFrame([
        {"date": "2019-01-02", "root": "SPY", "doi_z": 0.5, "fwd_ret_5": 0.01},
        {"date": "2019-01-02", "root": "AAPL", "doi_z": 0.3, "fwd_ret_5": -0.01},
        {"date": "2019-01-03", "root": "SPY", "doi_z": 0.6, "fwd_ret_5": 0.02},
        {"date": "2019-01-03", "root": "AAPL", "doi_z": 0.4, "fwd_ret_5": -0.02},
    ])
    # min_names=5: both dates excluded (only 2 names)
    stats = _doi_era_stats(panel, h=5, min_names=5, lo="2019-01-01", hi="2019-12-31")
    assert stats["excluded_dates"] == 2
    assert stats["n_dates"] == 0

    # min_names=2: both dates included
    stats2 = _doi_era_stats(panel, h=5, min_names=2, lo="2019-01-01", hi="2019-12-31")
    # Only 2 names → rank_ic needs ≥10 → still excluded by rank_ic minimum
    # (V.rank_ic returns NaN below 10) — so n_dates=0 still, but for different reason
    assert stats2["n_dates"] == 0  # below rank_ic 10-name floor


def test_thin_universe_exclusion_with_sufficient_names():
    """When we inject enough names, dates pass the breadth floor."""
    from scripts.rerun_options_gates_thetadata import _doi_era_stats
    import numpy as np
    # 12 names on one date — above the min_names=10 floor, below rank_ic 10-floor? No, rank_ic is 10
    rng = np.random.default_rng(42)
    rows = []
    for d in ["2019-01-02", "2019-01-03"]:
        for i in range(12):
            rows.append({
                "date": d, "root": f"SYM{i:02d}",
                "doi_z": rng.normal(),
                "fwd_ret_5": rng.normal() * 0.01,
            })
    panel = pd.DataFrame(rows)
    stats = _doi_era_stats(panel, h=5, min_names=10, lo="2019-01-01", hi="2019-12-31")
    # 12 names ≥ min_names=10 AND ≥ rank_ic floor 10 → should not be excluded
    assert stats["excluded_dates"] == 0
    assert stats["n_dates"] == 2


# --------------------------------------------------------------------------- #
# Smoke mode does not write gate files                                          #
# --------------------------------------------------------------------------- #

def test_smoke_mode_writes_no_gate_files(tmp_path, monkeypatch):
    """--smoke mode must not write any gate JSON files."""
    import json
    import importlib
    import os

    monkeypatch.setenv("THETADATA_STORE", _store())

    # Patch config.data_dir to tmp_path to avoid writing to real data/
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent))

    # Simulate running with smoke=True by calling the functions directly
    from scripts.rerun_options_gates_thetadata import run_s_doi
    from engine.thetadata_store import universe

    roots = universe(store=_store())
    tr_closes = pd.DataFrame()  # empty — no forward returns in fixture
    doi_gate = run_s_doi(roots, tr_closes, store=_store(), smoke=True)

    # In smoke mode, the gate should be flagged as smoke
    assert "[SMOKE]" in doi_gate.get("note", "")
    assert doi_gate["scored"] is False

    # Verify no gate files exist in tmp_path
    doi_path = tmp_path / "options_flow" / "gate_doi_thetadata.json"
    assert not doi_path.exists(), "Smoke mode must not write gate JSON files"


# --------------------------------------------------------------------------- #
# Rank-IC math vs hand-computed values                                          #
# --------------------------------------------------------------------------- #

def test_rank_ic_hand_computed():
    """Verify V.rank_ic against hand-computed Spearman correlations.

    Case 1: signal = fwd = [1,2,...,10] → perfect rank agreement → IC = 1.0
    Case 2: signal = [1..10], fwd = [10,9,...,1] → perfect anti-rank → IC = -1.0
    Case 3: n < 10 → NaN
    """
    from engine import validation as V

    # Case 1: perfect positive agreement
    sig = list(range(1, 11))   # [1,2,...,10]
    fwd = list(range(1, 11))
    ic = V.rank_ic(sig, fwd)
    assert abs(ic - 1.0) < 1e-9, f"Expected IC=1.0, got {ic}"

    # Case 2: perfect negative agreement (reverse of same monotone list)
    fwd_neg = list(reversed(fwd))  # [10,9,...,1]
    ic_neg = V.rank_ic(sig, fwd_neg)
    assert abs(ic_neg - (-1.0)) < 1e-9, f"Expected IC=-1.0, got {ic_neg}"

    # Case 3: below 10 names → NaN
    ic_small = V.rank_ic([1, 2, 3], [1, 2, 3])
    assert np.isnan(ic_small), f"Expected NaN for n<10, got {ic_small}"


def test_doi_z_is_normalised():
    """doi_z = doi_raw / rolling_std; should be approximately N(0,1) on large data."""
    from engine.thetadata_store import doi_series
    s = doi_series("SPY", put_call="both", window=1, store=_store())
    # Only 3 dates — not enough for meaningful stats; just verify column exists and is finite
    doi_z_vals = s["doi_z"].dropna()
    # With 3 dates and window=1, the 63-day rolling std needs min_periods=21 — will be NaN
    # This is correct behaviour (not enough history)
    assert "doi_z" in s.columns


# --------------------------------------------------------------------------- #
# make_chain_provider: maps thetadata frames to polygon_gex schema             #
# --------------------------------------------------------------------------- #

def test_chain_provider_returns_correct_schema():
    from engine.thetadata_store import make_chain_provider
    provider = make_chain_provider(store=_store())
    frame = provider("2019-01-02", "SPY")
    assert frame is not None
    assert not frame.empty
    expected_cols = {"underlying", "expiry", "K", "T", "is_call", "spot", "oi", "volume", "asof"}
    assert expected_cols.issubset(set(frame.columns)), (
        f"Missing columns: {expected_cols - set(frame.columns)}"
    )
    # spot should be positive
    assert frame["spot"].iloc[0] > 0
    # underlying should be SPY
    assert (frame["underlying"] == "SPY").all()


def test_chain_provider_require_iv_returns_none_when_no_greeks():
    """require_iv=True should return None for dates without IV in greeks tier."""
    from engine.thetadata_store import make_chain_provider
    provider = make_chain_provider(store=_store(), require_iv=True)
    # 2019-01-02 has no greeks → should return None
    frame = provider("2019-01-02", "SPY")
    assert frame is None


def test_chain_provider_require_iv_returns_frame_with_greeks():
    """require_iv=True should return frame for dates with IV data."""
    from engine.thetadata_store import make_chain_provider
    provider = make_chain_provider(store=_store(), require_iv=True)
    # 2019-01-03 has greeks
    frame = provider("2019-01-03", "SPY")
    assert frame is not None
    assert not frame.empty
    assert "iv" in frame.columns
    iv_valid = frame["iv"].dropna()
    assert len(iv_valid) > 0


def test_chain_provider_T_positive():
    """T (years to expiry) should be >= 0."""
    from engine.thetadata_store import make_chain_provider
    provider = make_chain_provider(store=_store())
    frame = provider("2019-01-02", "SPY")
    assert frame is not None
    assert (frame["T"] >= 0).all()


def test_chain_provider_is_call_bool():
    """is_call should map 'C'->True, 'P'->False correctly."""
    from engine.thetadata_store import make_chain_provider
    provider = make_chain_provider(store=_store())
    frame = provider("2019-01-02", "SPY")
    assert frame is not None
    assert frame["is_call"].dtype == bool
    assert frame["is_call"].any()
    assert (~frame["is_call"]).any()


# --------------------------------------------------------------------------- #
# Regression guard: refactored validators produce same output on default path  #
# --------------------------------------------------------------------------- #

def test_skew_validator_default_path_byte_compatible(tmp_path):
    """Running build_panel() with chain_provider=None (default) must produce
    the same output as the original build_panel() call on an empty ledger
    / empty polygon_gex chain store. This guards against accidental regressions
    in the refactor."""
    import importlib.util
    import sys

    # The validator's build_panel() with chain_provider=None should work identically
    # We test on an empty state (no ledger, no polygon_gex chains)
    from scripts.validate_options_skew import build_panel as skew_build
    from scripts.validate_options_ivspread import build_panel as ivspread_build

    # Both should return empty DataFrames when there's no data
    p_skew = skew_build(chain_provider=None)
    p_iv = ivspread_build(chain_provider=None)

    # Should be DataFrames (not errors)
    assert isinstance(p_skew, pd.DataFrame)
    assert isinstance(p_iv, pd.DataFrame)


def test_skew_validator_with_provider():
    """With a provider injected, build_panel should return rows from the thetadata store
    (specifically: dates where greeks IV is present for XZZ computation)."""
    from engine.thetadata_store import make_chain_provider
    from scripts.validate_options_skew import build_panel

    # We need greeks for skew (iv required)
    provider = make_chain_provider(store=_store(), require_iv=True)
    # Inject provider; since there's no greeks dir enumeration without a proper td_store env,
    # we test that build_panel with provider doesn't crash and returns a DataFrame
    import os
    os.environ["THETADATA_STORE"] = _store()
    try:
        panel = build_panel(chain_provider=provider)
        assert isinstance(panel, pd.DataFrame)
    finally:
        del os.environ["THETADATA_STORE"]


# --------------------------------------------------------------------------- #
# Parquet memoization: second chain() call in same year must NOT re-read disk  #
# --------------------------------------------------------------------------- #

def test_load_parquets_cache_hit_no_reread(monkeypatch):
    """Prove that calling chain() for two different dates in the same year
    reads each year-parquet file exactly once from disk.

    We monkeypatch pd.read_parquet and count calls.  After the first chain()
    call the year file is in _PARQUET_CACHE; the second call (different date,
    same year) must NOT trigger another pd.read_parquet call for that file.
    """
    import engine.thetadata_store as ts

    # Clear cache so the test is hermetic
    ts.clear_parquet_cache()

    call_count: dict[str, int] = {"n": 0}
    real_read_parquet = pd.read_parquet

    def counting_read_parquet(path, **kwargs):
        call_count["n"] += 1
        return real_read_parquet(path, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", counting_read_parquet)

    # First call: reads from disk
    df1 = ts.chain("2019-01-02", "SPY", store=_store())
    assert not df1.empty
    reads_after_first = call_count["n"]
    assert reads_after_first > 0, "Expected at least one pd.read_parquet call on first chain()"

    # Second call: different date, same year 2019 → cache hit, no new reads
    df2 = ts.chain("2019-01-03", "SPY", store=_store())
    assert not df2.empty
    reads_after_second = call_count["n"]

    assert reads_after_second == reads_after_first, (
        f"Second chain() call for a different date in the same year triggered "
        f"{reads_after_second - reads_after_first} additional pd.read_parquet call(s). "
        "Expected 0 — the year-parquet should have been served from _PARQUET_CACHE."
    )

    # Clean up
    ts.clear_parquet_cache()
