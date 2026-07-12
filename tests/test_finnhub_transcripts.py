"""Pure fixture-based tests for collectors/finnhub_transcripts.py.

No network calls — all HTTP interactions are either monkeypatched out or
supplied as canned JSON. Tests cover: parse logic, plan-gate handling,
PIT dedup store logic.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from collectors import finnhub_transcripts as FT


# ------------------------------------------------------------------ parse_transcript_list

def test_parse_basic_row():
    """A valid transcript item yields one flat row with expected fields."""
    raw = [{"id": "t123", "symbol": "AAPL", "title": "Q1 2026 Earnings Call",
            "time": "2026-04-25T21:00:00+0000", "quarter": 1, "year": 2026}]
    rows = FT.parse_transcript_list(raw, "AAPL")
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "AAPL"
    assert r["transcript_id"] == "t123"
    assert r["quarter"] == 1
    assert r["year"] == 2026
    assert r["event_time"] == "2026-04-25T21:00:00+0000"


def test_parse_skips_missing_id():
    """Items without an 'id' field are silently dropped."""
    raw = [{"symbol": "NVDA", "title": "No ID item"}]
    rows = FT.parse_transcript_list(raw, "NVDA")
    assert rows == []


def test_parse_empty_list():
    """Empty or None input returns empty list."""
    assert FT.parse_transcript_list([], "TSLA") == []
    assert FT.parse_transcript_list(None, "TSLA") == []  # type: ignore[arg-type]


def test_parse_multiple_rows():
    """Multiple items in one response all parse independently."""
    raw = [
        {"id": "a1", "title": "Q4 2025", "time": "2026-02-01T21:00:00Z", "quarter": 4, "year": 2025},
        {"id": "a2", "title": "Q1 2026", "time": "2026-05-01T21:00:00Z", "quarter": 1, "year": 2026},
    ]
    rows = FT.parse_transcript_list(raw, "MSFT")
    assert len(rows) == 2
    ids = {r["transcript_id"] for r in rows}
    assert ids == {"a1", "a2"}


# ------------------------------------------------------------------ plan-gate handling

def test_plan_gate_error_in_json_body(tmp_path, monkeypatch):
    """A 'permission' error in the JSON body sets plan_gated and returns ingest with flag."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "baskets").mkdir()
    (tmp_path / "baskets" / "membership.json").write_text(json.dumps({
        "baskets": {"tech": {"members": [{"ticker": "AAPL"}, {"ticker": "NVDA"}]}}
    }))

    adapter = FT.FinnhubTranscriptsAdapter.__new__(FT.FinnhubTranscriptsAdapter)
    adapter.api_key = "test_key"
    adapter._plan_gated = False
    adapter.name = FT.FinnhubTranscriptsAdapter.name
    adapter.group = FT.FinnhubTranscriptsAdapter.group

    permission_response = MagicMock()
    permission_response.json.return_value = {"error": "You don't have permission to access this endpoint."}
    permission_response.status_code = 200

    with patch.object(adapter, "http_get", return_value=permission_response):
        result = adapter._get_transcript_list("AAPL")
    assert result is None
    assert adapter._plan_gated is True


def test_plan_gate_stops_run_early(tmp_path, monkeypatch):
    """After a plan-gate trip, fetch() returns ingest row with plan_gated=True and 0 new rows."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "baskets").mkdir()
    (tmp_path / "baskets" / "membership.json").write_text(json.dumps({
        "baskets": {"tech": {"members": [{"ticker": "AAPL"}, {"ticker": "NVDA"}]}}
    }))

    adapter = FT.FinnhubTranscriptsAdapter.__new__(FT.FinnhubTranscriptsAdapter)
    adapter.api_key = "test_key"
    adapter._plan_gated = False
    adapter.name = FT.FinnhubTranscriptsAdapter.name
    adapter.group = FT.FinnhubTranscriptsAdapter.group
    adapter.stale_after_days = FT.FinnhubTranscriptsAdapter.stale_after_days

    # First call triggers plan gate; subsequent calls should not be made
    call_count = 0

    def mock_get_list(symbol):
        nonlocal call_count
        call_count += 1
        adapter._plan_gated = True
        return None

    with patch.object(adapter, "_get_transcript_list", side_effect=mock_get_list):
        result = adapter.fetch()

    ingest_df = result["finnhub_transcripts__ingest"]
    assert ingest_df["new_rows"].iloc[0] == 0
    assert ingest_df["plan_gated"].iloc[0] == True  # noqa: E712 — np.True_ needs ==, not `is`
    assert call_count == 1   # stopped after first None


# ------------------------------------------------------------------ store / PIT dedup

def test_merge_new_rows(tmp_path, monkeypatch):
    """_merge writes to parquet and returns row count."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    adapter = FT.FinnhubTranscriptsAdapter.__new__(FT.FinnhubTranscriptsAdapter)
    adapter.api_key = "k"
    adapter._plan_gated = False
    adapter.name = FT.FinnhubTranscriptsAdapter.name
    adapter.group = FT.FinnhubTranscriptsAdapter.group

    # _merge receives already-parsed rows (event_time is the post-parse field name)
    df = pd.DataFrame([
        {"ticker": "AAPL", "transcript_id": "t1", "title": "Q1 2026",
         "event_time": "2026-04-25T21:00:00Z", "quarter": 1, "year": 2026},
        {"ticker": "MSFT", "transcript_id": "t2", "title": "Q1 2026",
         "event_time": "2026-04-24T21:00:00Z", "quarter": 1, "year": 2026},
    ])
    n = adapter._merge(df)
    assert n == 2

    path = tmp_path / "finnhub" / "transcripts.parquet"
    assert path.exists()
    stored = pd.read_parquet(path)
    assert len(stored) == 2
    assert "_first_seen" in stored.columns


def test_merge_dedup_keeps_first(tmp_path, monkeypatch):
    """A second merge with the same (ticker, transcript_id) keeps the first row."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    adapter = FT.FinnhubTranscriptsAdapter.__new__(FT.FinnhubTranscriptsAdapter)
    adapter.api_key = "k"
    adapter._plan_gated = False
    adapter.name = FT.FinnhubTranscriptsAdapter.name
    adapter.group = FT.FinnhubTranscriptsAdapter.group

    # _merge receives already-parsed rows (event_time is the post-parse field name)
    df1 = pd.DataFrame([{"ticker": "AAPL", "transcript_id": "t1", "title": "Q1 orig",
                          "event_time": "2026-04-25T21:00:00Z", "quarter": 1, "year": 2026}])
    df2 = pd.DataFrame([{"ticker": "AAPL", "transcript_id": "t1", "title": "Q1 dup",
                          "event_time": "2026-04-25T21:00:00Z", "quarter": 1, "year": 2026}])
    adapter._merge(df1)
    adapter._merge(df2)

    stored = pd.read_parquet(tmp_path / "finnhub" / "transcripts.parquet")
    assert len(stored) == 1
    assert stored.iloc[0]["title"] == "Q1 orig"


def test_merge_empty_is_noop(tmp_path, monkeypatch):
    """_merge on an empty DataFrame returns 0 and writes nothing."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    adapter = FT.FinnhubTranscriptsAdapter.__new__(FT.FinnhubTranscriptsAdapter)
    adapter.api_key = "k"
    adapter._plan_gated = False
    adapter.name = FT.FinnhubTranscriptsAdapter.name
    adapter.group = FT.FinnhubTranscriptsAdapter.group

    n = adapter._merge(pd.DataFrame())
    assert n == 0
    assert not (tmp_path / "finnhub" / "transcripts.parquet").exists()


# ------------------------------------------------------------------ no-key gate

def test_no_key_sets_expected_failure(monkeypatch):
    """Without a Finnhub key, expected_failure is set (so runner reports 'blocked')."""
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_KEY", raising=False)
    from lib import config as cfg
    monkeypatch.setattr(cfg, "secret", lambda k: None)
    adapter = FT.FinnhubTranscriptsAdapter()
    assert adapter.expected_failure is not None
    with pytest.raises(RuntimeError, match="FINNHUB key not set"):
        adapter.fetch()


# ------------------------------------------------------------------ fetch window filter

def test_fetch_filters_stale_items_by_raw_time_key(tmp_path, monkeypatch):
    """fetch() must filter out items older than WINDOW_DAYS using the raw 'time' key.

    This test is DISCRIMINATING: it would fail against pre-fix code that filtered on
    'event_time' (which is always absent in raw items, making the window dead code and
    passing every item regardless of age).

    Raw Finnhub items carry 'time'; parse_transcript_list renames it to 'event_time'.
    The window filter in fetch() must operate on 'time' BEFORE parse_transcript_list.
    """
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "baskets").mkdir()
    (tmp_path / "baskets" / "membership.json").write_text(json.dumps({
        "baskets": {"tech": {"members": [{"ticker": "AAPL"}]}}
    }))

    # Two raw items using the REAL Finnhub API shape (key = "time", not "event_time")
    recent_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")
    stale_iso  = "2000-01-01T00:00:00+0000"   # clearly outside WINDOW_DAYS=90

    raw_items = [
        {"id": "recent1", "symbol": "AAPL", "title": "Recent Call",
         "time": recent_iso, "quarter": 1, "year": 2026},
        {"id": "stale1",  "symbol": "AAPL", "title": "Very Old Call",
         "time": stale_iso, "quarter": 4, "year": 1999},
    ]

    adapter = FT.FinnhubTranscriptsAdapter.__new__(FT.FinnhubTranscriptsAdapter)
    adapter.api_key = "test_key"
    adapter._plan_gated = False
    adapter.name = FT.FinnhubTranscriptsAdapter.name
    adapter.group = FT.FinnhubTranscriptsAdapter.group
    adapter.stale_after_days = FT.FinnhubTranscriptsAdapter.stale_after_days

    def mock_get_list(symbol):
        return raw_items

    with patch.object(adapter, "_get_transcript_list", side_effect=mock_get_list), \
         patch("time.sleep"):
        result = adapter.fetch()

    ingest = result["finnhub_transcripts__ingest"]
    assert ingest["new_rows"].iloc[0] == 1, (
        "Only the recent item should pass the 90-day window filter; "
        "stale item must be excluded. (Pre-fix code filtered on 'event_time' which is "
        "never present in raw items, making WINDOW_DAYS dead code and passing both items.)"
    )
