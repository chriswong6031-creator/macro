"""Tests for scripts/archive_context_snapshots.py.

Validates keep-FIRST semantics and absent-safety for every source.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.archive_context_snapshots import (
    _build_row,
    _append,
    _read_regime,
    _read_market_state,
    _read_fear_greed,
    ARCHIVE_FILE,
    main,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)


# ── _build_row ────────────────────────────────────────────────────────────────

def test_build_row_full():
    regime = {
        "date": "2026-07-06",
        "quad": "Q1",
        "liquidity_overlay": "neutral",
        "cycle_tag": "mid",
        "transition_state": "TRANSITIONING",
        "confidence": 0.42,
        "vol_regime": {"regime": "normalizing"},
    }
    ms = {"verdict": "RISK_OFF", "score": 40}
    row = _build_row(regime, ms, fear_greed=55.0)
    assert row["date"] == "2026-07-06"
    assert row["quad"] == "Q1"
    assert row["liquidity"] == "neutral"
    assert row["cycle_tag"] == "mid"
    assert row["transition_state"] == "TRANSITIONING"
    assert row["regime_confidence"] == pytest.approx(0.42)
    assert row["market_verdict"] == "RISK_OFF"
    assert row["market_score"] == 40
    assert row["vol_regime_verdict"] == "normalizing"
    assert row["fear_greed_composite"] == pytest.approx(55.0)


def test_build_row_absent_sources():
    """Empty dicts + None fear_greed -> all optional fields None (never crash)."""
    row = _build_row({}, {}, None)
    assert row["quad"] is None
    assert row["market_verdict"] is None
    assert row["fear_greed_composite"] is None
    # date falls back to UTC today string — just check it is a non-empty string
    assert isinstance(row["date"], str) and len(row["date"]) == 10


# ── _append keep-FIRST ────────────────────────────────────────────────────────

def test_append_creates_parquet_on_first_write(tmp_path):
    archive_path = tmp_path / ARCHIVE_FILE
    row = {"date": "2026-07-06", "quad": "Q1", "liquidity": "neutral",
           "cycle_tag": "mid", "transition_state": "CALM",
           "regime_confidence": 0.5, "market_verdict": "NEUTRAL",
           "market_score": 60, "vol_regime_verdict": "low", "fear_greed_composite": 50.0}
    written = _append(archive_path, row)
    assert written is True
    assert archive_path.exists()
    df = pd.read_parquet(archive_path)
    assert list(df["date"]) == ["2026-07-06"]
    assert df.loc[0, "quad"] == "Q1"


def test_append_keep_first_same_date(tmp_path):
    """Second write for the same date must be a no-op (keep-FIRST)."""
    archive_path = tmp_path / ARCHIVE_FILE
    row1 = {"date": "2026-07-06", "quad": "Q1", "liquidity": "neutral",
            "cycle_tag": "mid", "transition_state": "CALM",
            "regime_confidence": 0.5, "market_verdict": "RISK_ON",
            "market_score": 70, "vol_regime_verdict": "low", "fear_greed_composite": 60.0}
    row2 = {**row1, "quad": "Q9"}  # same date, different quad
    _append(archive_path, row1)
    written2 = _append(archive_path, row2)
    assert written2 is False
    df = pd.read_parquet(archive_path)
    assert df["quad"].tolist() == ["Q1"]  # original row preserved


def test_append_different_dates_accumulate(tmp_path):
    """Each new date appends a new row."""
    archive_path = tmp_path / ARCHIVE_FILE
    for d in ["2026-07-04", "2026-07-05", "2026-07-06"]:
        row = {"date": d, "quad": "Q2", "liquidity": "loose",
               "cycle_tag": "early", "transition_state": "STABLE",
               "regime_confidence": 0.7, "market_verdict": "RISK_ON",
               "market_score": 80, "vol_regime_verdict": "low", "fear_greed_composite": 55.0}
        _append(archive_path, row)
    df = pd.read_parquet(archive_path)
    assert list(df["date"]) == ["2026-07-04", "2026-07-05", "2026-07-06"]


# ── absent-safety ─────────────────────────────────────────────────────────────

def test_read_regime_absent(tmp_path):
    """Missing file returns empty dict, never crashes."""
    d = _read_regime(tmp_path)
    assert d == {}


def test_read_market_state_absent(tmp_path):
    d = _read_market_state(tmp_path)
    assert d == {}


def test_read_fear_greed_absent(tmp_path):
    result = _read_fear_greed(tmp_path)
    assert result is None


def test_read_fear_greed_present(tmp_path):
    """Reads the most recent fear_greed value from parquet."""
    df = pd.DataFrame({"fear_greed": [20, 22, 25]},
                      index=pd.to_datetime(["2026-07-03", "2026-07-04", "2026-07-05"]))
    df.index.name = "date"
    _write_parquet(tmp_path / "sentiment_crypto" / "fear_greed.parquet", df.reset_index())
    result = _read_fear_greed(tmp_path)
    assert result == pytest.approx(25.0)


# ── main() integration ────────────────────────────────────────────────────────

def test_main_absent_safe(tmp_path, monkeypatch):
    """main() must exit 0 with no source files present."""
    monkeypatch.setattr("scripts.archive_context_snapshots.config.data_dir", lambda: tmp_path)
    rc = main()
    assert rc == 0


def test_main_writes_and_keep_first(tmp_path, monkeypatch):
    """main() writes one row then is a no-op on re-run for the same date."""
    monkeypatch.setattr("scripts.archive_context_snapshots.config.data_dir", lambda: tmp_path)
    regime = {
        "date": "2026-07-06", "quad": "Q1", "liquidity_overlay": "neutral",
        "cycle_tag": "mid", "transition_state": "CALM", "confidence": 0.55,
        "vol_regime": {"regime": "low"},
    }
    ms = {"verdict": "RISK_ON", "score": 75}
    _write_json(tmp_path / "regime" / "latest.json", regime)
    _write_json(tmp_path / "market_state" / "latest.json", ms)

    rc1 = main()
    assert rc1 == 0
    archive = tmp_path / "signal_archive" / ARCHIVE_FILE
    assert archive.exists()
    df = pd.read_parquet(archive)
    assert len(df) == 1
    assert df.loc[0, "quad"] == "Q1"

    rc2 = main()
    assert rc2 == 0
    df2 = pd.read_parquet(archive)
    assert len(df2) == 1  # keep-FIRST: no duplicate row added
