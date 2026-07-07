"""Tests for d2_comment_letter_release_phase0 -- pure logic, no network.

Tests:
  1. build_reviews: gap rule (AM-2) correctly splits reviews at 180-day boundary
  2. substance classification: 0/1/2 UPLOAD -> light; >=3 -> substantive (AM-1)
  3. date_collapsed_nw: collapses multiple same-date obs to one before NW
  4. beta estimation: returns None when insufficient data
  5. fwd_ret: handles edge cases (insufficient forward data)
  6. run_split_half: within-cell median split (not global-median)
  7. _get_ar_col_gate: ALL stores use plain beta-adj ar (pre-registered metric)
  8. ledger path is throwaway (not canonical trial_ledger.jsonl)
  9. apply_massive_sanity_filter: drops |AR|>100% outliers from massive leg
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.d2_comment_letter_release_phase0 import (  # noqa: E402
    build_reviews,
    date_collapsed_nw,
    run_split_half,
    _get_ar_col_gate,
    apply_massive_sanity_filter,
    LEDGER_PATH,
    REVIEW_GAP_DAYS,
    SUBSTANTIVE_MIN_UPLOADS,
    LIGHT_MAX_UPLOADS,
    MASSIVE_AR_ABS_MAX,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a minimal filings DataFrame
# ─────────────────────────────────────────────────────────────────────────────
def _make_filings(cik: int, dates_and_types: list[tuple[str, str]]) -> pd.DataFrame:
    rows = []
    for d, ft in dates_and_types:
        rows.append({"cik": cik, "form_type": ft, "date_filed": pd.Timestamp(d),
                     "company_name": "TESTCO", "file_name": "edgar/data/test.txt"})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# 1. AM-2 gap rule: filings > 180 days apart should be separate reviews
# ─────────────────────────────────────────────────────────────────────────────
def test_gap_rule_creates_two_reviews():
    """Two sets of filings more than 180 days apart should produce 2 events."""
    filings = _make_filings(12345, [
        ("2020-01-10", "UPLOAD"),
        ("2020-02-15", "CORRESP"),   # same review (36 days later)
        ("2020-10-01", "UPLOAD"),    # >180 days from last => new review
        ("2020-10-20", "CORRESP"),
    ])
    cik_ticker = {12345: "TEST"}
    reviews = build_reviews(filings, cik_ticker)
    assert len(reviews) == 2, f"Expected 2 reviews, got {len(reviews)}"


def test_gap_rule_same_review_within_180():
    """Filings within 180 days should stay in one review."""
    filings = _make_filings(12345, [
        ("2020-01-10", "UPLOAD"),
        ("2020-06-15", "CORRESP"),  # 156 days => same review
        ("2020-07-01", "UPLOAD"),   # 16 more days => still same review
    ])
    cik_ticker = {12345: "TEST"}
    reviews = build_reviews(filings, cik_ticker)
    assert len(reviews) == 1, f"Expected 1 review, got {len(reviews)}"


def test_gap_rule_exactly_at_boundary():
    """Exactly 181 days apart should be a new review (> 180)."""
    filings = _make_filings(99999, [
        ("2020-01-01", "UPLOAD"),
        ("2020-07-01", "CORRESP"),  # 182 days => new review
    ])
    cik_ticker = {99999: "BNDRY"}
    reviews = build_reviews(filings, cik_ticker)
    assert len(reviews) == 2, f"Expected 2 reviews at gap>180, got {len(reviews)}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Substance classification
# ─────────────────────────────────────────────────────────────────────────────
def test_substance_zero_upload_is_light():
    """AM-1: 0 UPLOADs => substance=light."""
    filings = _make_filings(11111, [
        ("2021-03-01", "CORRESP"),
        ("2021-03-15", "CORRESP"),
    ])
    cik_ticker = {11111: "NOUPLOA"}
    reviews = build_reviews(filings, cik_ticker)
    assert len(reviews) == 1
    assert reviews.iloc[0]["substance"] == "light", "0 uploads should be light"
    assert reviews.iloc[0]["n_upload"] == 0


def test_substance_two_upload_is_light():
    """2 UPLOADs => substance=light (boundary value)."""
    filings = _make_filings(22222, [
        ("2021-03-01", "UPLOAD"),
        ("2021-03-10", "CORRESP"),
        ("2021-03-20", "UPLOAD"),  # 2nd upload
        ("2021-03-30", "CORRESP"),
    ])
    cik_ticker = {22222: "LGHT2"}
    reviews = build_reviews(filings, cik_ticker)
    assert len(reviews) == 1
    assert reviews.iloc[0]["n_upload"] == 2
    assert reviews.iloc[0]["substance"] == "light"


def test_substance_three_upload_is_substantive():
    """3+ UPLOADs => substance=substantive (pre-registration: SUBSTANTIVE_MIN_UPLOADS=3)."""
    filings = _make_filings(33333, [
        ("2021-03-01", "UPLOAD"),
        ("2021-03-10", "CORRESP"),
        ("2021-03-20", "UPLOAD"),
        ("2021-03-28", "CORRESP"),
        ("2021-04-05", "UPLOAD"),   # 3rd upload
        ("2021-04-15", "CORRESP"),
    ])
    cik_ticker = {33333: "SUBST"}
    reviews = build_reviews(filings, cik_ticker)
    assert len(reviews) == 1
    assert reviews.iloc[0]["n_upload"] == 3
    assert reviews.iloc[0]["substance"] == "substantive"


# ─────────────────────────────────────────────────────────────────────────────
# 3. date_collapsed_nw: collapse then NW
# ─────────────────────────────────────────────────────────────────────────────
def test_date_collapsed_nw_collapses_multiple_events_per_date():
    """Multiple events on the same date should produce exactly one obs in the NW series."""
    # 20 dates with 3 events each, all with the same AR per date
    rng = np.random.default_rng(42)
    dates = pd.date_range("2022-01-01", periods=20, freq="W")
    rows = []
    for d in dates:
        for _ in range(3):
            rows.append({"t0": d, "ar_h5": float(rng.normal(0.01, 0.05))})
    df = pd.DataFrame(rows)
    result = date_collapsed_nw(df, "ar_h5")
    # n_dates should be 20, not 60
    assert result["n_dates"] == 20, f"Expected 20 dates, got {result['n_dates']}"
    assert result["n"] == 60, f"Expected 60 raw events, got {result['n']}"
    assert result.get("t") is not None


def test_date_collapsed_nw_insufficient_dates():
    """Fewer than 8 dates should return t=None (can't do NW)."""
    rows = [{"t0": pd.Timestamp("2022-01-01") + pd.Timedelta(days=i*7),
             "ar_h5": 0.01} for i in range(5)]
    df = pd.DataFrame(rows)
    result = date_collapsed_nw(df, "ar_h5")
    assert result["n_dates"] == 5
    assert result.get("t") is None


def test_date_collapsed_nw_empty():
    """Empty DataFrame should return zeros gracefully."""
    df = pd.DataFrame(columns=["t0", "ar_h5"])
    result = date_collapsed_nw(df, "ar_h5")
    assert result["n"] == 0
    assert result["n_dates"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Review event date = first filing date
# ─────────────────────────────────────────────────────────────────────────────
def test_event_date_is_first_filing():
    """Event date must be the FIRST filing date in the review."""
    filings = _make_filings(55555, [
        ("2021-06-15", "CORRESP"),   # filed second
        ("2021-06-01", "UPLOAD"),    # filed first (earlier date)
        ("2021-07-01", "UPLOAD"),
    ])
    cik_ticker = {55555: "EVTDT"}
    reviews = build_reviews(filings, cik_ticker)
    assert len(reviews) == 1
    assert reviews.iloc[0]["event_date"] == pd.Timestamp("2021-06-01")


# ─────────────────────────────────────────────────────────────────────────────
# 5. No ticker -> has_ticker = False
# ─────────────────────────────────────────────────────────────────────────────
def test_unmapped_cik_has_ticker_false():
    """CIK not in cik_ticker map should have has_ticker=False and ticker=None."""
    filings = _make_filings(99991, [("2021-01-01", "UPLOAD")])
    cik_ticker = {}  # empty map
    reviews = build_reviews(filings, cik_ticker)
    assert not reviews.iloc[0]["has_ticker"]
    assert reviews.iloc[0]["ticker"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Pre-registration constant checks
# ─────────────────────────────────────────────────────────────────────────────
def test_prereg_constants():
    """Frozen pre-registration constants must match the spec."""
    assert REVIEW_GAP_DAYS == 180, "AM-2 gap rule must be 180 days"
    assert SUBSTANTIVE_MIN_UPLOADS == 3, "Substantive threshold must be 3"
    assert LIGHT_MAX_UPLOADS == 2, "Light max must be 2"


# ---------------------------------------------------------------------------
# 7. _get_ar_col_gate: ALL stores use plain beta-adj ar (pre-registered metric)
# ---------------------------------------------------------------------------
def test_get_ar_col_gate_yahoo_uses_plain_ar():
    """Yahoo store gate metric must be plain beta-adj ar (NOT excess_ar).

    The pre-registered gate metric is beta-adjusted AR vs SPY for BOTH stores.
    The excess_ar peer-baseline is exploratory/post-hoc only and must not
    be used in gate computation.
    """
    assert _get_ar_col_gate("yahoo", "h5") == "ar_h5"
    assert _get_ar_col_gate("yahoo", "h21") == "ar_h21"


def test_get_ar_col_gate_massive_uses_plain_ar():
    """Massive store gate metric must be plain beta-adj ar."""
    assert _get_ar_col_gate("massive", "h5") == "ar_h5"
    assert _get_ar_col_gate("massive", "h21") == "ar_h21"


# ─────────────────────────────────────────────────────────────────────────────
# 8. run_split_half: within-cell median split, not global median
# ─────────────────────────────────────────────────────────────────────────────
def _make_results_df(store: str, substance: str, dates: list, ar_values: list) -> pd.DataFrame:
    """Build a minimal results DataFrame for split-half testing."""
    rows = []
    for d, ar in zip(dates, ar_values):
        rows.append({
            "store": store,
            "substance": substance,
            "t0": pd.Timestamp(d),
            "ar_h5": ar,
            "ar_h21": ar,
            "excess_ar_h5": ar,
            "excess_ar_h21": ar,
        })
    return pd.DataFrame(rows)


def test_split_half_uses_within_cell_median():
    """Split-half must split on EACH cell's own median, not the global median.

    If yahoo events are all in 2005-2010 and massive events are all in 2022-2025,
    a global median split puts ALL yahoo events in the first half (n_second=0 for yahoo)
    and ALL massive events in the second half (n_first=0 for massive). The within-cell
    split should give each store ~half its events in each half.
    """
    import pandas as pd
    # Yahoo: 20 events spread 2005-2010 (all before 2021)
    yahoo_dates = [f"200{y}-06-01" for y in range(5, 10)] * 4
    yahoo_df = _make_results_df("yahoo", "substantive", yahoo_dates, [0.01] * 20)

    # Massive: 20 events spread 2022-2024 (all after 2021)
    massive_dates = [f"202{y}-06-01" for y in range(2, 5)] * 7
    massive_dates = massive_dates[:20]
    massive_df = _make_results_df("massive", "substantive", massive_dates, [0.01] * 20)

    combined = pd.concat([yahoo_df, massive_df], ignore_index=True)

    result = run_split_half(combined)

    # Each store should have events in BOTH halves (within-cell split)
    yahoo_first = result.get("first_substantive_h5_yahoo", {})
    yahoo_second = result.get("second_substantive_h5_yahoo", {})
    massive_first = result.get("first_substantive_h5_massive", {})
    massive_second = result.get("second_substantive_h5_massive", {})

    # Both halves should have some events (not zero)
    assert yahoo_first.get("n", 0) > 0, "Yahoo first half should have events (within-cell split)"
    assert yahoo_second.get("n", 0) > 0, "Yahoo second half should have events (within-cell split)"
    assert massive_first.get("n", 0) > 0, "Massive first half should have events (within-cell split)"
    assert massive_second.get("n", 0) > 0, "Massive second half should have events (within-cell split)"


# ---------------------------------------------------------------------------
# 9. apply_massive_sanity_filter: drops |AR|>100% outliers
# ---------------------------------------------------------------------------
def test_sanity_filter_drops_massive_outliers():
    """Massive events with |ar_h5| > 100% should be dropped; yahoo untouched."""
    rows = [
        {"store": "massive", "substance": "light", "t0": pd.Timestamp("2022-01-01"),
         "ar_h5": 50.0,   "ar_h21": 0.01},  # ar_h5 = 5000% -- outlier
        {"store": "massive", "substance": "light", "t0": pd.Timestamp("2022-01-05"),
         "ar_h5": 0.02,   "ar_h21": 0.01},  # clean
        {"store": "yahoo",   "substance": "light", "t0": pd.Timestamp("2010-01-01"),
         "ar_h5": 0.01,   "ar_h21": 0.01},  # yahoo: never filtered
    ]
    df = pd.DataFrame(rows)
    filtered, stats = apply_massive_sanity_filter(df)
    assert stats["n_massive_dropped"] == 1, f"Expected 1 dropped, got {stats}"
    assert stats["n_massive_kept"] == 1
    # Yahoo row must survive
    assert len(filtered[filtered["store"] == "yahoo"]) == 1
    # The clean massive row must survive
    assert len(filtered[filtered["store"] == "massive"]) == 1
    # The outlier massive row must be gone
    assert (filtered[filtered["store"] == "massive"]["ar_h5"] < 2.0).all()


def test_sanity_filter_constant():
    """MASSIVE_AR_ABS_MAX must be 1.0 (100% threshold)."""
    assert MASSIVE_AR_ABS_MAX == 1.0, f"Expected 1.0, got {MASSIVE_AR_ABS_MAX}"


def test_sanity_filter_does_not_touch_yahoo():
    """Yahoo events with large |AR| should NOT be filtered (filter is massive-only)."""
    rows = [
        {"store": "yahoo", "substance": "substantive", "t0": pd.Timestamp("2010-01-01"),
         "ar_h5": 2.5, "ar_h21": -1.5},  # large AR but yahoo -- should survive
    ]
    df = pd.DataFrame(rows)
    filtered, stats = apply_massive_sanity_filter(df)
    assert stats.get("n_massive_total", 0) == 0
    assert len(filtered) == 1  # yahoo row untouched


# ---------------------------------------------------------------------------
# 10. LEDGER_PATH is a throwaway local path (not canonical trial_ledger.jsonl)
# ---------------------------------------------------------------------------
def test_ledger_path_is_not_canonical():
    """LEDGER_PATH must NOT point at the canonical data/trial_ledger.jsonl.

    The canonical ledger is a tracked shared file. Writing to it from a
    worktree script dirties it on every run (house-law violation).
    """
    # The canonical path fragment that must NOT appear
    canonical_fragment = "data/trial_ledger.jsonl"
    # Our path must not resolve to the canonical name
    assert LEDGER_PATH.name != "trial_ledger.jsonl", (
        f"LEDGER_PATH {LEDGER_PATH} resolves to the canonical trial_ledger.jsonl — "
        "use a throwaway local name instead"
    )
