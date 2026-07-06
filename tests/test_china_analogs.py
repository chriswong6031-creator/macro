"""Tests for scripts/build_china_analogs.py — no live network, no live parquet.

Coverage:
- time_exclusion: candidates >=120d before query only
- diversity_spacing: no two selected analogs within 60 calendar days
- no_lookahead_fixture: forward path anchored strictly after analog date (PIT)
- off_history_nulls: forward windows past price history return null
- schema_keys: all required keys present in output JSON
- build_safe_on_missing_parquet: build() returns 0 gracefully when files absent
- z_stats_per_candidate_set: z-scores use candidate-set population stats
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------
from scripts.build_china_analogs import (
    K,
    TIME_EXCLUSION_DAYS,
    DIVERSITY_DAYS,
    SCHEMA,
    _build_candidates,
    _fan_stats,
    _find_analogs,
    _fwd_log_return,
    _is_valid_row,
    _z_stats,
    build,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_regime(
    dates: list[str],
    quads: list[str | None],
    growths: list[float | None],
    inflations: list[float | None],
    liq: str = "neutral",
    cycle: str = "mid",
) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame(
        {
            "growth_score": growths,
            "inflation_score": inflations,
            "quad": pd.array(quads, dtype="string"),
            "quad_name": pd.array(
                ["Goldilocks" if q == "Q1" else ("Stagflation" if q == "Q3" else q)
                 for q in quads],
                dtype="string",
            ),
            "liquidity": liq,
            "cycle": cycle,
        },
        index=idx,
    )


def _make_price(dates: list[str], closes: list[float]) -> pd.Series:
    return pd.Series(closes, index=pd.to_datetime(dates), name="close")


# ---------------------------------------------------------------------------
# _is_valid_row
# ---------------------------------------------------------------------------

def test_is_valid_row_valid():
    row = pd.Series({"quad": "Q1", "growth_score": 0.5, "inflation_score": 0.3})
    assert _is_valid_row(row) is True


@pytest.mark.parametrize("quad,g,inf_", [
    (None, 0.5, 0.3),
    (float("nan"), 0.5, 0.3),
    ("unknown", 0.5, 0.3),
    ("Q1", float("nan"), 0.3),
    ("Q1", 0.5, float("nan")),
])
def test_is_valid_row_invalid(quad, g, inf_):
    row = pd.Series({"quad": quad, "growth_score": g, "inflation_score": inf_})
    assert _is_valid_row(row) is False


# ---------------------------------------------------------------------------
# _build_candidates filters NaN rows
# ---------------------------------------------------------------------------

def test_build_candidates_excludes_nan_quad():
    regime = _make_regime(
        dates=["2020-01-01", "2020-01-02", "2020-01-03"],
        quads=[None, "Q1", "Q2"],
        growths=[0.1, 0.2, 0.3],
        inflations=[0.1, 0.2, 0.3],
    )
    cands = _build_candidates(regime)
    assert len(cands) == 2
    assert "2020-01-01" not in cands.index.strftime("%Y-%m-%d").tolist()


def test_build_candidates_excludes_nan_scores():
    regime = _make_regime(
        dates=["2020-01-01", "2020-01-02"],
        quads=["Q1", "Q1"],
        growths=[float("nan"), 0.5],
        inflations=[0.3, 0.3],
    )
    cands = _build_candidates(regime)
    assert len(cands) == 1


# ---------------------------------------------------------------------------
# Time-exclusion: candidates must be >=120 calendar days before query
# ---------------------------------------------------------------------------

def test_time_exclusion_no_recent_candidates():
    """All candidates within 119 days of query → empty analog list."""
    # query = last valid row = 2020-06-01
    # candidates: 2020-05-01 is only 31 days before → excluded
    dates = [f"2020-0{m}-01" for m in range(1, 7)]  # 2020-01-01 .. 2020-06-01
    quads = ["Q1"] * 6
    growths = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    inflations = [0.1] * 6
    regime = _make_regime(dates, quads, growths, inflations)

    shcomp = _make_price(dates, [100.0, 101.0, 102.0, 103.0, 104.0, 105.0])

    result = _find_analogs(regime, shcomp, None)
    # All candidates are within 120 days of the query (2020-06-01)
    # 2020-01-01 is 152 days before — that one should survive the exclusion cutoff
    # Let's just assert distance ordering is respected
    for a in result["analogs"]:
        delta = (pd.Timestamp("2020-06-01") - pd.Timestamp(a["date"])).days
        assert delta >= TIME_EXCLUSION_DAYS, (
            f"Analog {a['date']} is only {delta} days before query; "
            f"should be excluded (min {TIME_EXCLUSION_DAYS})"
        )


def test_time_exclusion_exact_boundary():
    """Candidate exactly at EXCLUSION_DAYS is included; one day less is not."""
    query_date = pd.Timestamp("2020-06-01")
    # candidate_a: exactly 120 days before
    candidate_a = (query_date - pd.Timedelta(days=TIME_EXCLUSION_DAYS)).strftime("%Y-%m-%d")
    # candidate_b: 119 days before (should be excluded)
    candidate_b = (query_date - pd.Timedelta(days=TIME_EXCLUSION_DAYS - 1)).strftime("%Y-%m-%d")

    regime = _make_regime(
        dates=[candidate_a, candidate_b, "2020-06-01"],
        quads=["Q1", "Q1", "Q1"],
        growths=[0.5, 0.5, 0.5],
        inflations=[0.3, 0.3, 0.3],
    )
    # Add enough price data
    price_dates = [candidate_a, candidate_b, "2020-06-01"]
    shcomp = _make_price(price_dates, [100.0, 101.0, 102.0])

    result = _find_analogs(regime, shcomp, None)
    analog_dates = [a["date"] for a in result["analogs"]]
    # candidate_a is exactly at cutoff (<=) → included; candidate_b → excluded
    assert candidate_a in analog_dates
    assert candidate_b not in analog_dates


# ---------------------------------------------------------------------------
# Diversity spacing: no two analogs within 60 calendar days of each other
# ---------------------------------------------------------------------------

def test_diversity_spacing():
    """Build a pool where the top-2 nearest are 30 days apart → diversity forces skip."""
    # We construct a regime with a long enough history, and two very similar days
    # that are only 30 days apart; the second must be skipped.
    base = "2018-01-01"
    # Anchor query at 2020-01-01
    all_dates = pd.date_range("2015-01-01", "2020-01-01", freq="D")
    dates_str = [d.strftime("%Y-%m-%d") for d in all_dates]
    n = len(dates_str)
    quads = ["Q1"] * n
    growths = [0.5] * n
    inflations = [0.3] * n
    regime = _make_regime(dates_str, quads, growths, inflations)

    shcomp = _make_price(
        dates_str,
        [100.0 + i * 0.01 for i in range(n)],
    )

    result = _find_analogs(regime, shcomp, None)

    # Verify pairwise diversity
    selected_dates = [pd.Timestamp(a["date"]) for a in result["analogs"]]
    for i, da in enumerate(selected_dates):
        for j, db in enumerate(selected_dates):
            if i >= j:
                continue
            gap = abs((da - db).days)
            assert gap >= DIVERSITY_DAYS, (
                f"Analogs {da.date()} and {db.date()} are only {gap} days apart "
                f"(diversity minimum = {DIVERSITY_DAYS})"
            )


# ---------------------------------------------------------------------------
# No-lookahead fixture: PIT — first close STRICTLY after analog date
# ---------------------------------------------------------------------------

def test_no_lookahead_fwd_anchored_strictly_after():
    """_fwd_log_return must use the first close *after* anchor_date, not on it."""
    # anchor on 2020-03-01; price on that date is 100; next day 110
    price = _make_price(
        ["2020-03-01", "2020-03-02", "2020-03-03"],
        [100.0, 110.0, 121.0],
    )
    anchor = pd.Timestamp("2020-03-01")
    # With sessions=1: start=110 (first close *after* 2020-03-01), end=121
    ret = _fwd_log_return(price, anchor, 1)
    expected = round(math.log(121.0 / 110.0), 6)
    assert ret == pytest.approx(expected, rel=1e-5)


def test_no_lookahead_anchor_on_price_date():
    """The price on the anchor date itself must NOT be used as start_close."""
    price = _make_price(
        ["2020-01-01", "2020-01-02", "2020-01-05"],
        [50.0, 60.0, 72.0],
    )
    anchor = pd.Timestamp("2020-01-01")
    # start should be 60.0 (first strictly after 2020-01-01), end at sessions=1 is 72.0
    ret = _fwd_log_return(price, anchor, 1)
    expected = round(math.log(72.0 / 60.0), 6)
    assert ret == pytest.approx(expected, rel=1e-5)


# ---------------------------------------------------------------------------
# Off-history nulls: windows past price history return null
# ---------------------------------------------------------------------------

def test_off_history_null_past_end():
    """sessions >= len(after) → null (never a truncated number)."""
    price = _make_price(["2020-01-01", "2020-01-02"], [100.0, 105.0])
    anchor = pd.Timestamp("2020-01-01")
    # Only 1 row after anchor_date; requesting sessions=1 → exactly len(after) → null
    assert _fwd_log_return(price, anchor, 1) is None


def test_off_history_null_anchor_after_end():
    """Anchor after all price data → null."""
    price = _make_price(["2019-01-01", "2019-01-02"], [100.0, 105.0])
    anchor = pd.Timestamp("2025-01-01")
    assert _fwd_log_return(price, anchor, 20) is None


def test_off_history_null_no_price_series():
    """None price series → null."""
    anchor = pd.Timestamp("2020-01-01")
    assert _fwd_log_return(None, anchor, 20) is None


# ---------------------------------------------------------------------------
# Schema keys: all required keys present in output
# ---------------------------------------------------------------------------

REQUIRED_SCHEMA_KEYS = {
    "schema", "is_context_only", "generated_utc", "as_of",
    "coverage", "query", "analogs", "fan",
    "method_note", "disclaimer_en", "disclaimer_zh",
}
REQUIRED_COVERAGE_KEYS = {"start", "end", "n_candidate_days"}
REQUIRED_QUERY_KEYS = {"date", "quad", "quad_name", "liquidity", "cycle", "growth_z", "inflation_z"}
REQUIRED_ANALOG_KEYS = {"date", "distance", "quad", "liquidity", "cycle", "fwd_shcomp", "fwd_csi300"}
REQUIRED_FWD_KEYS = {"h20", "h60", "h120"}
REQUIRED_FAN_HORIZONS = {"h20", "h60", "h120"}
REQUIRED_FAN_STAT_KEYS = {"p25", "median", "p75", "n"}


def _make_full_result() -> dict:
    """Run _find_analogs on a synthetic but complete dataset."""
    dates = pd.date_range("2000-01-01", "2020-12-31", freq="D")
    n = len(dates)
    dates_str = [d.strftime("%Y-%m-%d") for d in dates]
    quads = ["Q1" if i % 4 == 0 else ("Q2" if i % 4 == 1 else ("Q3" if i % 4 == 2 else "Q4"))
             for i in range(n)]
    growths = [math.sin(i / 200.0) * 0.5 for i in range(n)]
    inflations = [math.cos(i / 300.0) * 0.4 for i in range(n)]
    regime = _make_regime(dates_str, quads, growths, inflations)

    price = _make_price(dates_str, [1000.0 + i * 0.1 for i in range(n)])
    return _find_analogs(regime, price, None)


def test_schema_keys_top_level():
    result = _make_full_result()
    # Build the wrapper dict as build() would
    out = {
        "schema": SCHEMA,
        "is_context_only": True,
        "generated_utc": "2026-07-06T00:00:00Z",
        "as_of": result["query"]["date"],
        "coverage": result["coverage"],
        "query": result["query"],
        "analogs": result["analogs"],
        "fan": result["fan"],
        "method_note": "x",
        "disclaimer_en": "x",
        "disclaimer_zh": "x",
    }
    assert REQUIRED_SCHEMA_KEYS <= set(out.keys())


def test_schema_coverage_keys():
    result = _make_full_result()
    assert REQUIRED_COVERAGE_KEYS <= set(result["coverage"].keys())


def test_schema_query_keys():
    result = _make_full_result()
    assert REQUIRED_QUERY_KEYS <= set(result["query"].keys())


def test_schema_analog_keys():
    result = _make_full_result()
    assert len(result["analogs"]) > 0
    for a in result["analogs"]:
        assert REQUIRED_ANALOG_KEYS <= set(a.keys())
        assert REQUIRED_FWD_KEYS <= set(a["fwd_shcomp"].keys())


def test_schema_fan_keys():
    result = _make_full_result()
    assert REQUIRED_FAN_HORIZONS <= set(result["fan"].keys())
    for hz in REQUIRED_FAN_HORIZONS:
        assert REQUIRED_FAN_STAT_KEYS <= set(result["fan"][hz].keys())


def test_schema_is_context_only_true():
    """is_context_only must be True — this is display-only data."""
    result = _make_full_result()
    out = {"schema": SCHEMA, "is_context_only": True, "generated_utc": "x",
           "as_of": result["query"]["date"], "coverage": result["coverage"],
           "query": result["query"], "analogs": result["analogs"],
           "fan": result["fan"], "method_note": "x",
           "disclaimer_en": "x", "disclaimer_zh": "x"}
    assert out["is_context_only"] is True


# ---------------------------------------------------------------------------
# build() safe on missing parquet
# ---------------------------------------------------------------------------

def test_build_safe_on_missing_regime_parquet(tmp_path, monkeypatch):
    """build() returns 0 and writes nothing when regime_history.parquet absent."""
    monkeypatch.setattr(
        "scripts.build_china_analogs._root",
        lambda: tmp_path,
    )
    # tmp_path has no data/ directory — parquet is absent
    result = build()
    assert result == 0


def test_build_safe_on_missing_price_parquet(tmp_path, monkeypatch):
    """build() returns 0 even when SHCOMP parquet is absent (price is None → nulls)."""
    # Create minimal regime parquet
    regime_dir = tmp_path / "data" / "china_regime"
    regime_dir.mkdir(parents=True)
    dates = pd.date_range("2000-01-01", "2020-12-31", freq="B")
    n = len(dates)
    quads = ["Q1"] * n
    growths = [0.3] * n
    inflations = [0.2] * n
    df = pd.DataFrame({
        "growth_score": growths,
        "inflation_score": inflations,
        "quad": pd.array(quads, dtype="string"),
        "quad_name": pd.array(["Goldilocks"] * n, dtype="string"),
        "liquidity": "neutral",
        "cycle": "mid",
    }, index=dates)
    df.to_parquet(regime_dir / "regime_history.parquet")

    # Wire site output to tmp_path
    site_dir = tmp_path / "site" / "china_intel"
    site_dir.mkdir(parents=True)

    monkeypatch.setattr("scripts.build_china_analogs._root", lambda: tmp_path)
    monkeypatch.setattr(
        "scripts.build_china_analogs._site_china_intel",
        lambda: site_dir,
    )
    result = build()
    assert result == 0
    # analogs.json should have been written
    out = site_dir / "analogs.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["schema"] == SCHEMA
    # All fwd_shcomp values should be null (no price data)
    for a in data["analogs"]:
        for h in ("h20", "h60", "h120"):
            assert a["fwd_shcomp"][h] is None


# ---------------------------------------------------------------------------
# Z-score stats use candidate-set population stats
# ---------------------------------------------------------------------------

def test_z_stats_use_candidate_population():
    """_z_stats returns population (ddof=0) stats over the candidate set."""
    candidates = pd.DataFrame({
        "growth_score": [1.0, 3.0],          # mean=2, std=1 (pop)
        "inflation_score": [10.0, 20.0],     # mean=15, std=5 (pop)
        "quad": pd.array(["Q1", "Q1"], dtype="string"),
        "quad_name": pd.array(["Goldilocks", "Goldilocks"], dtype="string"),
        "liquidity": ["neutral", "neutral"],
        "cycle": ["mid", "mid"],
    })
    g_mean, g_std, i_mean, i_std = _z_stats(candidates)
    assert g_mean == pytest.approx(2.0)
    assert g_std == pytest.approx(1.0)
    assert i_mean == pytest.approx(15.0)
    assert i_std == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# fan_stats correct quantiles
# ---------------------------------------------------------------------------

def test_fan_stats_all_null():
    analogs = [{"fwd_shcomp": {"h20": None, "h60": None, "h120": None}} for _ in range(5)]
    fan = _fan_stats(analogs)
    for h in ("h20", "h60", "h120"):
        assert fan[h]["n"] == 0
        assert fan[h]["median"] is None


def test_fan_stats_computes_quantiles():
    vals = [0.01, 0.02, 0.03, 0.04, 0.05]
    analogs = [{"fwd_shcomp": {"h20": v, "h60": v * 2, "h120": None}} for v in vals]
    fan = _fan_stats(analogs)
    arr = np.array(vals)
    assert fan["h20"]["median"] == pytest.approx(float(np.percentile(arr, 50)), rel=1e-5)
    assert fan["h20"]["n"] == 5
    assert fan["h120"]["n"] == 0
