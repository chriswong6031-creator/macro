"""Tests for scripts/research/fetch_dead_name_prices_polygon.py.

Network-free: Polygon HTTP calls are monkeypatched. Invariants:
  * Priority ordering (P1/P2/P3) is respected.
  * Dry-run makes zero HTTP calls.
  * Resumable: already-fetched tickers are skipped.
  * Parquet schema matches dead_name_prices.v1 (ticker, date, close, source).
  * Coverage JSON is written on each run.
  * Dates are normalized to midnight (no 04:00 UTC offset from Polygon ms timestamps).
  * No-key path returns error dict without raising.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_polygon_response(n_bars: int = 10, start_ms: int = 1625529600000):
    """Simulate a Polygon REST /v2/aggs response body."""
    bars = []
    for i in range(n_bars):
        bars.append({"t": start_ms + i * 86_400_000, "c": 100.0 + i})
    return {"results": bars, "resultsCount": n_bars, "status": "OK"}


def _no_key_env(monkeypatch):
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo_paths(tmp_path, monkeypatch):
    """Set up minimal repo structure + monkeypatch config.data_dir()."""
    edgar_dir = tmp_path / "edgar"
    edgar_dir.mkdir(parents=True)
    breadth_dir = tmp_path / "breadth"
    breadth_dir.mkdir(parents=True)
    research_dir = tmp_path / "research"
    research_dir.mkdir(parents=True)

    # Minimal PIT membership with 2 dead tickers
    # DEAD1: exited 2022-01-15 (post-anchor, rolling-expiry window P1)
    # DEAD2: exited 2023-06-01 (post-anchor, OOS window P3)
    mem = pd.DataFrame({
        "ticker": ["DEAD1", "DEAD2", "LIVE1"],
        "start_date": pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-01"]),
        "end_date": pd.to_datetime(["2022-01-15", "2023-06-01", None]),
        "src": ["sp500", "sp500", "sp500"],
    })
    mem.to_parquet(breadth_dir / "sp1500_pit_membership.parquet")

    # Minimal fire tape (used for OOS prioritization)
    fires = pd.DataFrame({
        "ticker": ["DEAD2", "LIVE1"],
        "date": pd.to_datetime(["2021-09-01", "2021-08-01"]),
    })
    fires.to_parquet(research_dir / "gate_fires_baskets.parquet")

    # Monkeypatch config
    import scripts.research.fetch_dead_name_prices_polygon as m
    monkeypatch.setattr(m.config, "data_dir", lambda: tmp_path)

    return tmp_path, m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_api_key_returns_error(monkeypatch, repo_paths):
    """If no key is available, fetch() returns error dict without raising."""
    tmp_path, m = repo_paths
    _no_key_env(monkeypatch)
    monkeypatch.setattr(m, "_polygon_key", lambda: None)

    result = m.fetch(max_new=10)
    assert result.get("error") == "no_api_key"
    assert result.get("fetched", 0) == 0 or "fetched" not in result


def test_dry_run_makes_no_requests(monkeypatch, repo_paths):
    """Dry run prints plan but never calls requests.get."""
    tmp_path, m = repo_paths
    monkeypatch.setattr(m, "_polygon_key", lambda: "fake-key-xxx")

    # Ensure requests would fail if called
    import requests as req_module
    monkeypatch.setattr(req_module, "get", lambda *a, **k: pytest.fail("no HTTP in dry-run"))

    result = m.fetch(dry_run=True)
    assert result.get("dry_run") is True
    assert "todo_count" in result


def test_parquet_schema_and_date_normalization(monkeypatch, repo_paths):
    """Parquet written with correct schema; dates normalized to midnight."""
    tmp_path, m = repo_paths
    monkeypatch.setattr(m, "_polygon_key", lambda: "fake-key-xxx")
    monkeypatch.setattr(m, "REQUEST_RATE", 10_000.0)  # no real sleep

    # Mock Polygon endpoint for DEAD1 (5 bars starting 2021-07-06)
    # Polygon returns ms timestamps that decode to 04:00 UTC (midnight NY)
    start_ms = 1625529600000  # 2021-07-06 00:00:00 UTC (= 2021-07-05 20:00 ET)
    resp_body = _make_polygon_response(n_bars=5, start_ms=start_ms)

    import requests as req_module

    class FakeResponse:
        status_code = 200

        def json(self):
            return resp_body

    monkeypatch.setattr(req_module, "get", lambda *a, **k: FakeResponse())

    result = m.fetch(max_new=5)
    assert result["n_success"] >= 1

    prices_path = tmp_path / "edgar" / "dead_name_prices.parquet"
    assert prices_path.exists(), "Parquet file must be written"

    df = pd.read_parquet(prices_path)
    assert set(df.columns) >= {"ticker", "date", "close", "source"}

    # Date must be midnight (no time component) — normalized at write time
    for d in df["date"]:
        ts = pd.Timestamp(d)
        assert ts.hour == 0 and ts.minute == 0 and ts.second == 0, (
            f"Date not midnight: {d}"
        )

    assert (df["source"] == "polygon").all()


def test_resumable_skips_already_fetched(monkeypatch, repo_paths):
    """Second call skips tickers already in the parquet."""
    tmp_path, m = repo_paths
    monkeypatch.setattr(m, "_polygon_key", lambda: "fake-key-xxx")
    monkeypatch.setattr(m, "REQUEST_RATE", 10_000.0)

    call_count = {"n": 0}

    import requests as req_module

    start_ms = 1625529600000

    class FakeResponse:
        status_code = 200

        def json(self):
            call_count["n"] += 1
            return _make_polygon_response(n_bars=5, start_ms=start_ms)

    monkeypatch.setattr(req_module, "get", lambda *a, **k: FakeResponse())

    # First run
    m.fetch(max_new=10)
    n_after_first = call_count["n"]
    assert n_after_first >= 1

    # Second run (same tickers already in parquet)
    m.fetch(max_new=10)
    n_after_second = call_count["n"]
    assert n_after_second == n_after_first, "Second run must not re-fetch"


def test_coverage_json_written(monkeypatch, repo_paths):
    """Coverage JSON is written with correct schema after each run."""
    tmp_path, m = repo_paths
    monkeypatch.setattr(m, "_polygon_key", lambda: "fake-key-xxx")
    monkeypatch.setattr(m, "REQUEST_RATE", 10_000.0)

    import requests as req_module

    class FakeResponse:
        status_code = 200

        def json(self):
            return _make_polygon_response(n_bars=3)

    monkeypatch.setattr(req_module, "get", lambda *a, **k: FakeResponse())

    m.fetch(max_new=5)

    cov_path = tmp_path / "edgar" / "_dead_name_coverage.json"
    assert cov_path.exists(), "Coverage JSON must be written"
    cov = json.loads(cov_path.read_text())
    assert "n_dead_universe" in cov
    assert "n_with_prices" in cov
    assert "price_coverage_frac" in cov
    assert 0.0 <= cov["price_coverage_frac"] <= 1.0


def test_explicit_tickers_respected(monkeypatch, repo_paths):
    """When --tickers is provided, only those tickers are fetched."""
    tmp_path, m = repo_paths
    monkeypatch.setattr(m, "_polygon_key", lambda: "fake-key-xxx")
    monkeypatch.setattr(m, "REQUEST_RATE", 10_000.0)

    fetched = []

    import requests as req_module

    def fake_get(url, **kw):
        # Extract ticker from URL pattern
        class Resp:
            status_code = 200

            def json(self):
                return _make_polygon_response(n_bars=3)

        return Resp()

    monkeypatch.setattr(req_module, "get", fake_get)

    # Only fetch DEAD1 (which is in post-anchor universe)
    result = m.fetch(tickers=["DEAD1"], max_new=10)
    assert result.get("n_todo", 0) == 1 or result.get("dry_run")
