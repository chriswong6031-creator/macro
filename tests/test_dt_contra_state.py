"""tests/test_dt_contra_state.py — DT-NW-1 builder tests.

Tests
-----
1. schema_required_keys      — emitted JSON contains all required top-level keys.
2. state_enum                — every state value in the states list is one of
                               {fade, bounce, neutral} or None (unknown chip state).
3. graceful_absent_dir       — when the stockdata dir does not exist, build() writes
                               a valid degraded JSON with empty states and never raises.
4. deterministic_ordering    — states list is sorted alphabetically by ticker.
5. counts_match_states       — counts_by_state sums to n_with_chip.
6. caveat_from_chip_module   — caveat string matches engine.dannytrades_chip._CAVEAT
                               (single source of truth, DT-R11a).
7. normal_path_with_fixture  — given a tmp stockdata dir with a handful of synthetic
                               ticker JSONs, build() produces correct aggregate counts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_dt_contra_state import build, _VALID_STATES
from engine.dannytrades_chip import _CAVEAT as CHIP_CAVEAT

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _write_ticker_json(directory: Path, ticker: str, dt_contra: dict | None) -> None:
    """Write a minimal per-ticker stockdata JSON file."""
    payload: dict = {"ticker": ticker, "price": 100.0}
    if dt_contra is not None:
        payload["dt_contra"] = dt_contra
    (directory / f"{ticker}.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_chip(state: str, band: str, score_pct: float = 0.75,
               whale: float = 55.0, whale_chg: float = 8.0) -> dict:
    return {
        "state": state,
        "band": band,
        "score_pct": round(score_pct, 3),
        "whale": whale,
        "whale_chg": whale_chg,
    }


# ---------------------------------------------------------------------------
#  Test 1: required keys
# ---------------------------------------------------------------------------

def test_schema_required_keys(tmp_path):
    """Emitted JSON must contain all required top-level keys."""
    stockdata = tmp_path / "stockdata"
    stockdata.mkdir()
    _write_ticker_json(stockdata, "AAPL", _make_chip("fade", "extended"))

    with mock.patch("scripts.build_dt_contra_state._REPO_ROOT", tmp_path):
        result = build(stockdata_dir=stockdata)

    required = {"asof", "universe_n", "n_with_chip", "counts_by_state",
                "counts_by_band", "states", "caveat"}
    missing = required - set(result.keys())
    assert not missing, f"Missing required keys: {missing}"


# ---------------------------------------------------------------------------
#  Test 2: state enum validation
# ---------------------------------------------------------------------------

def test_state_enum(tmp_path):
    """Every state value in states list must be one of the valid states or None."""
    stockdata = tmp_path / "stockdata"
    stockdata.mkdir()
    _write_ticker_json(stockdata, "AAPL", _make_chip("fade", "extended"))
    _write_ticker_json(stockdata, "MSFT", _make_chip("bounce", "washed"))
    _write_ticker_json(stockdata, "NVDA", _make_chip("neutral", "neutral"))
    _write_ticker_json(stockdata, "GOOG", None)   # no dt_contra field

    with mock.patch("scripts.build_dt_contra_state._REPO_ROOT", tmp_path):
        result = build(stockdata_dir=stockdata)

    valid_states = _VALID_STATES | {None}
    for row in result["states"]:
        assert row["state"] in valid_states, (
            f"ticker {row['ticker']}: unexpected state {row['state']!r}"
        )

    # Exactly 3 tickers have chips
    assert result["n_with_chip"] == 3
    assert result["universe_n"] == 4


# ---------------------------------------------------------------------------
#  Test 3: graceful degradation when stockdata dir is absent
# ---------------------------------------------------------------------------

def test_graceful_absent_dir(tmp_path):
    """build() must not raise and must write a valid degraded JSON when dir is absent."""
    absent_dir = tmp_path / "nonexistent_stockdata"
    # Do NOT create absent_dir — it must not exist.

    with mock.patch("scripts.build_dt_contra_state._REPO_ROOT", tmp_path):
        (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
        result = build(stockdata_dir=absent_dir)

    assert result is not None, "build() must return a dict even when dir is absent"
    assert result["universe_n"] == 0
    assert result["n_with_chip"] == 0
    assert result["states"] == []
    assert "note" in result, "degraded output must carry a 'note' key"

    # Must also have written the JSON file
    out_path = tmp_path / "data" / "neuralweb" / "dt_contra_state.json"
    assert out_path.exists(), "degraded JSON must be written to disk"
    parsed = json.loads(out_path.read_text())
    assert parsed["universe_n"] == 0
    assert parsed["states"] == []


# ---------------------------------------------------------------------------
#  Test 4: deterministic ordering
# ---------------------------------------------------------------------------

def test_deterministic_ordering(tmp_path):
    """States list must be sorted alphabetically by ticker."""
    stockdata = tmp_path / "stockdata"
    stockdata.mkdir()
    for ticker in ["TSLA", "AAPL", "META", "GOOG", "AMZN"]:
        _write_ticker_json(stockdata, ticker, _make_chip("neutral", "neutral"))

    with mock.patch("scripts.build_dt_contra_state._REPO_ROOT", tmp_path):
        result = build(stockdata_dir=stockdata)

    tickers = [r["ticker"] for r in result["states"]]
    assert tickers == sorted(tickers), (
        f"states list is not sorted by ticker: {tickers}"
    )


# ---------------------------------------------------------------------------
#  Test 5: counts_by_state sums to n_with_chip
# ---------------------------------------------------------------------------

def test_counts_match_states(tmp_path):
    """Sum of counts_by_state values must equal n_with_chip."""
    stockdata = tmp_path / "stockdata"
    stockdata.mkdir()
    chips = [
        ("AAPL", "fade",    "extended"),
        ("MSFT", "fade",    "extended"),
        ("NVDA", "bounce",  "washed"),
        ("GOOG", "neutral", "neutral"),
        ("AMZN", "neutral", "elevated"),
    ]
    for ticker, state, band in chips:
        _write_ticker_json(stockdata, ticker, _make_chip(state, band))
    _write_ticker_json(stockdata, "NO_CHIP", None)  # no chip

    with mock.patch("scripts.build_dt_contra_state._REPO_ROOT", tmp_path):
        result = build(stockdata_dir=stockdata)

    total_from_counts = sum(result["counts_by_state"].values())
    assert total_from_counts == result["n_with_chip"], (
        f"counts_by_state total ({total_from_counts}) != n_with_chip ({result['n_with_chip']})"
    )
    assert result["counts_by_state"].get("fade") == 2
    assert result["counts_by_state"].get("bounce") == 1
    assert result["counts_by_state"].get("neutral") == 2


# ---------------------------------------------------------------------------
#  Test 6: caveat sourced from chip module (DT-R11a single-source-of-truth)
# ---------------------------------------------------------------------------

def test_caveat_from_chip_module(tmp_path):
    """caveat field must match engine.dannytrades_chip._CAVEAT verbatim."""
    stockdata = tmp_path / "stockdata"
    stockdata.mkdir()

    with mock.patch("scripts.build_dt_contra_state._REPO_ROOT", tmp_path):
        result = build(stockdata_dir=stockdata)

    assert result["caveat"] == CHIP_CAVEAT, (
        "caveat field does not match engine.dannytrades_chip._CAVEAT — "
        "this breaks the single-source-of-truth requirement (DT-R11a)"
    )


# ---------------------------------------------------------------------------
#  Test 7: normal path with synthetic fixture
# ---------------------------------------------------------------------------

def test_normal_path_with_fixture(tmp_path):
    """Full happy-path test with a synthetic stockdata directory."""
    stockdata = tmp_path / "stockdata"
    stockdata.mkdir()

    fixture_chips = [
        ("AAPL", _make_chip("fade",    "extended", score_pct=0.85, whale=65.0, whale_chg=12.0)),
        ("MSFT", _make_chip("bounce",  "washed",   score_pct=0.15, whale=30.0, whale_chg=-8.0)),
        ("NVDA", _make_chip("fade",    "elevated",  score_pct=0.70, whale=58.0, whale_chg=6.0)),
        ("GOOG", _make_chip("neutral", "neutral",  score_pct=0.50, whale=50.0, whale_chg=2.0)),
    ]
    for ticker, chip in fixture_chips:
        _write_ticker_json(stockdata, ticker, chip)
    # Two tickers with no chip at all
    _write_ticker_json(stockdata, "XYZ1", None)
    _write_ticker_json(stockdata, "XYZ2", None)

    with mock.patch("scripts.build_dt_contra_state._REPO_ROOT", tmp_path):
        result = build(stockdata_dir=stockdata)

    assert result["universe_n"] == 6
    assert result["n_with_chip"] == 4
    assert result["counts_by_state"] == {"bounce": 1, "fade": 2, "neutral": 1}
    assert result["counts_by_band"] == {"elevated": 1, "extended": 1, "neutral": 1, "washed": 1}

    # spot-check ordered output
    tickers = [r["ticker"] for r in result["states"]]
    assert tickers == ["AAPL", "GOOG", "MSFT", "NVDA"]

    # verify individual fields of one row
    aapl = next(r for r in result["states"] if r["ticker"] == "AAPL")
    assert aapl["state"] == "fade"
    assert aapl["band"] == "extended"
    assert aapl["score_pct"] == pytest.approx(0.85)
    assert aapl["whale"] == pytest.approx(65.0)
    assert aapl["whale_chg"] == pytest.approx(12.0)
