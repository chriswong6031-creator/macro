"""Unit tests for scripts/backfill_cctv_daily.py.

All tests use monkeypatched akshare — NO live network calls.

Coverage:
  1. resume-skip: already-present dates are not re-fetched
  2. empty-day marker: empty days get SENTINEL_EMPTY row, are skipped on re-run
  3. month-file routing: dates route to YYYY-MM.parquet correctly
  4. SIGTERM flush: _SIGTERM_RECEIVED flag stops the loop after current date
  5. content_sha256: computed correctly for real rows; empty for sentinels
  6. repair mode: sentinel-only dates ARE re-fetched when --repair is set
  7. error-day marker: network error produces SENTINEL_ERROR row
  8. stub detection: stub content produces SENTINEL_STUB title
  9. schema columns: shard contains the required columns

Run: .venv/bin/python -m pytest tests/test_backfill_cctv_daily.py -v
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.backfill_cctv_daily as mod  # noqa: E402
from scripts.backfill_cctv_daily import (  # noqa: E402
    SENTINEL_EMPTY,
    SENTINEL_ERROR,
    SENTINEL_STUB,
    _already_present,
    _is_retriable,
    _load_shard,
    _sentinel_row,
    _shard_path,
    _sha256,
    _upsert_day,
    fetch_day,
    run_backfill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw(items: list[tuple[str, str]]) -> pd.DataFrame:
    """Build a fixture matching akshare's news_cctv() DataFrame shape."""
    return pd.DataFrame({
        "date": ["20250115"] * len(items),
        "title": [t for t, _ in items],
        "content": [c for _, c in items],
    })


_REAL_ITEMS = [
    ("改革开放推进经济发展", "支持就业，促进增长，民生红利"),
    ("科技创新向好", "高质量发展，信心提振"),
]
_STUB_CONTENT = "对不起，可能是网络原因或无此页面"


# ---------------------------------------------------------------------------
# 1. Resume-skip
# ---------------------------------------------------------------------------

def test_resume_skip_already_present() -> None:
    """Dates already in the shard are not re-fetched."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        dt = date(2025, 1, 15)

        # Pre-populate with real data
        rows = [{
            "date": "2025-01-15", "seq": 0,
            "title": "改革", "content": "增长",
            "content_sha256": _sha256("改革增长"),
            "_fetched_at": "2025-01-16T00:00:00Z",
        }]
        _upsert_day(store, dt, rows)
        assert _already_present(store, dt)

        # A mocked akshare should NOT be called because the loop skips it
        mock_ak = MagicMock()
        mock_ak.news_cctv.return_value = _make_raw(_REAL_ITEMS)
        call_count_before = mock_ak.news_cctv.call_count

        with patch.dict("sys.modules", {"akshare": mock_ak}):
            run_backfill(store, start=dt, end=dt, max_days=10, pace_min=0, pace_max=0)

        # akshare.news_cctv should never have been called (date already present)
        assert mock_ak.news_cctv.call_count == call_count_before


# ---------------------------------------------------------------------------
# 2. Empty-day marker
# ---------------------------------------------------------------------------

def test_empty_day_gets_sentinel_row() -> None:
    """fetch_day returning empty DataFrame produces a SENTINEL_EMPTY row on upsert."""
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = pd.DataFrame()

    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 12))

    assert status == "empty"
    assert rows == []   # fetch_day itself returns empty list for empty days

    # Caller (run_backfill) converts this to a sentinel — replicate that:
    dt = date(2025, 1, 12)
    sentinel = _sentinel_row(dt, SENTINEL_EMPTY)
    assert sentinel["title"] == SENTINEL_EMPTY
    assert sentinel["content_sha256"] == ""
    assert sentinel["seq"] == 0


def test_empty_day_sentinel_is_skipped_on_rerun() -> None:
    """A date with only SENTINEL_EMPTY rows is treated as already-present and skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        dt = date(2025, 1, 12)
        _upsert_day(store, dt, [_sentinel_row(dt, SENTINEL_EMPTY)])
        assert _already_present(store, dt)
        assert _is_retriable(store, dt)   # empty sentinel IS retriable

        # In normal (non-repair) mode it should be SKIPPED
        mock_ak = MagicMock()
        mock_ak.news_cctv.return_value = pd.DataFrame()
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            run_backfill(store, start=dt, end=dt, repair=False, max_days=5,
                         pace_min=0, pace_max=0)
        # Should not have called akshare for this date
        assert mock_ak.news_cctv.call_count == 0


def test_empty_day_refetched_in_repair_mode() -> None:
    """In --repair mode, SENTINEL_EMPTY dates ARE re-fetched."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        dt = date(2025, 1, 12)
        _upsert_day(store, dt, [_sentinel_row(dt, SENTINEL_EMPTY)])

        mock_ak = MagicMock()
        mock_ak.news_cctv.return_value = _make_raw(_REAL_ITEMS)
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            run_backfill(store, start=dt, end=dt, repair=True, max_days=5,
                         pace_min=0, pace_max=0)
        assert mock_ak.news_cctv.call_count == 1


# ---------------------------------------------------------------------------
# 3. Month-file routing
# ---------------------------------------------------------------------------

def test_month_file_routing() -> None:
    """Dates route to YYYY-MM.parquet based on their year-month."""
    store = Path("/tmp/_cctv_test_routing_dummy")  # virtual path, no disk
    assert _shard_path(store, date(2023, 11, 5)) == store / "2023-11.parquet"
    assert _shard_path(store, date(2016, 2, 3)) == store / "2016-02.parquet"
    assert _shard_path(store, date(2025, 12, 31)) == store / "2025-12.parquet"


def test_two_dates_same_month_in_one_shard() -> None:
    """Both 2025-01-14 and 2025-01-15 land in 2025-01.parquet."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        for day in [14, 15]:
            dt = date(2025, 1, day)
            _upsert_day(store, dt, [{
                "date": f"2025-01-{day:02d}", "seq": 0,
                "title": "test", "content": "增长",
                "content_sha256": _sha256("test增长"),
                "_fetched_at": "2025-01-16T00:00:00Z",
            }])
        shard = _load_shard(store / "2025-01.parquet")
        assert len(shard) == 2
        assert set(shard["date"].tolist()) == {"2025-01-14", "2025-01-15"}


# ---------------------------------------------------------------------------
# 4. SIGTERM flush
# ---------------------------------------------------------------------------

def test_sigterm_stops_loop_after_current_date() -> None:
    """When _SIGTERM_RECEIVED is True, the loop breaks after at most 1 fetch."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)

        mock_ak = MagicMock()
        mock_ak.news_cctv.return_value = _make_raw(_REAL_ITEMS)

        original_flag = mod._SIGTERM_RECEIVED
        try:
            # Simulate SIGTERM having been received before the loop starts
            mod._SIGTERM_RECEIVED = True
            with patch.dict("sys.modules", {"akshare": mock_ak}):
                # Window has 3 dates; with SIGTERM set they should all be skipped
                run_backfill(store,
                             start=date(2025, 1, 13), end=date(2025, 1, 15),
                             pace_min=0, pace_max=0)
            # No fetches should have happened
            assert mock_ak.news_cctv.call_count == 0
        finally:
            mod._SIGTERM_RECEIVED = original_flag


# ---------------------------------------------------------------------------
# 5. content_sha256
# ---------------------------------------------------------------------------

def test_content_sha256_computed_for_real_rows() -> None:
    """sha256 of (title + content) is stored for ok rows."""
    title, content = "改革开放推进经济发展", "支持就业，促进增长，民生红利"
    expected = hashlib.sha256((title + content).encode("utf-8")).hexdigest()
    assert _sha256(title + content) == expected

    raw = _make_raw([(title, content)])
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = raw
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15))
    assert status == "ok"
    assert rows[0]["content_sha256"] == expected


def test_content_sha256_empty_for_sentinels() -> None:
    """Sentinel rows (empty/error/stub) have content_sha256 = ''."""
    dt = date(2025, 1, 15)
    for kind in (SENTINEL_EMPTY, SENTINEL_ERROR, SENTINEL_STUB):
        row = _sentinel_row(dt, kind, "detail")
        assert row["content_sha256"] == "", f"expected empty sha256 for {kind}"


# ---------------------------------------------------------------------------
# 6. Repair mode — error days
# ---------------------------------------------------------------------------

def test_error_day_sentinel_detected() -> None:
    """SENTINEL_ERROR rows are correctly identified as retriable."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        dt = date(2025, 1, 15)
        _upsert_day(store, dt, [_sentinel_row(dt, SENTINEL_ERROR, "timeout")])
        assert _already_present(store, dt)
        assert _is_retriable(store, dt)


def test_error_day_from_fetch_day() -> None:
    """fetch_day on a network error returns (row, 'error') with SENTINEL_ERROR title."""
    mock_ak = MagicMock()
    mock_ak.news_cctv.side_effect = Exception("connection refused")
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15), retries=1)
    assert status == "error"
    assert len(rows) == 1
    assert rows[0]["title"] == SENTINEL_ERROR
    assert "connection refused" in rows[0]["content"]
    assert rows[0]["content_sha256"] == ""


# ---------------------------------------------------------------------------
# 7. Stub detection
# ---------------------------------------------------------------------------

def test_stub_rows_get_sentinel_title() -> None:
    """Rows with stub content get title=SENTINEL_STUB and empty sha256."""
    raw = pd.DataFrame({
        "date": ["20250115"],
        "title": [""],
        "content": [_STUB_CONTENT],
    })
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = raw
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15))
    assert status == "stub"
    assert rows[0]["title"] == SENTINEL_STUB
    assert rows[0]["content_sha256"] == ""


def test_real_content_not_stub() -> None:
    """Normal news content is not mis-classified as a stub."""
    raw = _make_raw(_REAL_ITEMS)
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = raw
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15))
    assert status == "ok"
    for r in rows:
        assert r["title"] != SENTINEL_STUB


# ---------------------------------------------------------------------------
# 8. Schema columns
# ---------------------------------------------------------------------------

def test_schema_columns_present_in_shard() -> None:
    """Written shard contains all required schema columns."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        dt = date(2025, 1, 15)
        raw = _make_raw(_REAL_ITEMS)
        mock_ak = MagicMock()
        mock_ak.news_cctv.return_value = raw
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            rows, _ = fetch_day(dt)
        _upsert_day(store, dt, rows)
        shard = _load_shard(_shard_path(store, dt))

        required = {"date", "seq", "title", "content", "content_sha256", "_fetched_at"}
        assert required.issubset(set(shard.columns)), (
            f"Missing columns: {required - set(shard.columns)}"
        )


# ---------------------------------------------------------------------------
# 9. max_days stops the loop
# ---------------------------------------------------------------------------

def test_max_days_limits_fetches() -> None:
    """--max-days N stops after N actual fetches (not counting skips)."""
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)

        mock_ak = MagicMock()
        mock_ak.news_cctv.return_value = _make_raw(_REAL_ITEMS)
        with patch.dict("sys.modules", {"akshare": mock_ak}):
            # Window has 10 dates; max_days=3 should stop after 3 fetches
            run_backfill(store,
                         start=date(2025, 1, 6), end=date(2025, 1, 15),
                         max_days=3, pace_min=0, pace_max=0)
        assert mock_ak.news_cctv.call_count == 3


# ---------------------------------------------------------------------------
# 10. seq ordering preserved
# ---------------------------------------------------------------------------

def test_seq_ordering_preserved() -> None:
    """Broadcast order (seq column) is preserved through upsert."""
    items = [
        ("联播头条：经济稳增长", "支持就业"),   # seq 0
        ("第二条：科技创新", "高质量发展"),      # seq 1
        ("第三条：外交动态", "合作共赢"),        # seq 2
    ]
    raw = _make_raw(items)
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = raw
    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, _ = fetch_day(date(2025, 1, 15))

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        dt = date(2025, 1, 15)
        _upsert_day(store, dt, rows)
        shard = _load_shard(_shard_path(store, dt))
        day = shard[shard["date"] == "2025-01-15"].sort_values("seq")
        assert list(day["seq"]) == [0, 1, 2]
        assert day.iloc[0]["title"] == "联播头条：经济稳增长"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [
        test_resume_skip_already_present,
        test_empty_day_gets_sentinel_row,
        test_empty_day_sentinel_is_skipped_on_rerun,
        test_empty_day_refetched_in_repair_mode,
        test_month_file_routing,
        test_two_dates_same_month_in_one_shard,
        test_sigterm_stops_loop_after_current_date,
        test_content_sha256_computed_for_real_rows,
        test_content_sha256_empty_for_sentinels,
        test_error_day_sentinel_detected,
        test_error_day_from_fetch_day,
        test_stub_rows_get_sentinel_title,
        test_real_content_not_stub,
        test_schema_columns_present_in_shard,
        test_max_days_limits_fetches,
        test_seq_ordering_preserved,
    ]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
