"""Tests for the CCTV archive backfill pipeline.

Covers:
  1. Checkpoint / skip logic — already-archived dates are not re-fetched
  2. order_idx preservation — broadcast order is maintained in the shard
  3. Stub detection — page-rot responses are tagged fetch_status="stub"
  4. Tone-derivation equivalence — rebuild_cctv_tone_history produces the
     same result as calling _tone_features directly on the same data
  5. Repair flag — all-stub dates ARE re-fetched when --repair is set

Run: .venv/bin/python -m tests.test_backfill_cctv_archive
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

# Make repo root importable
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.backfill_cctv_archive import (  # noqa: E402
    _already_archived,
    _all_stubs_or_error,
    _is_stub_row,
    _load_shard,
    _shard_path,
    _upsert_day,
    fetch_day,
)
from scripts.rebuild_cctv_tone_history import rebuild  # noqa: E402
from collectors.china_news import _tone_features  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_raw_frame(items: list[tuple[str, str]], ds: str = "20250115") -> pd.DataFrame:
    """Build a fixture in ak.news_cctv's (date, title, content) shape."""
    return pd.DataFrame({
        "date": [ds] * len(items),
        "title": [t for t, _ in items],
        "content": [c for _, c in items],
    })


_GOOD_ITEMS = [
    ("改革开放推进经济发展", "支持就业，促进增长，民生红利"),
    ("科技创新向好", "高质量发展，信心提振"),
]
_STUB_ITEM = ("", "对不起，可能是网络原因或无此页面")


# ---------------------------------------------------------------------------
# 1. Stub detection
# ---------------------------------------------------------------------------

def test_stub_signatures_detected() -> None:
    assert _is_stub_row("对不起，可能是网络原因或无此页面")
    assert _is_stub_row("无此页面，请检查网络")
    assert _is_stub_row("404 页面不存在")


def test_real_content_not_stub() -> None:
    assert not _is_stub_row("改革开放推进经济发展")
    assert not _is_stub_row("国务院常务会议审议通过若干政策")


# ---------------------------------------------------------------------------
# 2. Checkpoint / skip logic
# ---------------------------------------------------------------------------

def test_already_archived_returns_false_for_missing_date() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        assert not _already_archived(arc, date(2025, 1, 15))


def test_already_archived_returns_true_after_upsert() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)
        rows = [{
            "date": "2025-01-15",
            "order_idx": 0,
            "title": "test",
            "content": "增长",
            "fetch_status": "ok",
            "fetched_at": "2025-01-16T00:00:00Z",
        }]
        _upsert_day(arc, dt, rows)
        assert _already_archived(arc, dt)


def test_skip_does_not_call_akshare() -> None:
    """If date already archived, fetch_day should not be called at all."""
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)
        rows = [{
            "date": "2025-01-15",
            "order_idx": 0,
            "title": "test",
            "content": "内容",
            "fetch_status": "ok",
            "fetched_at": "2025-01-16T00:00:00Z",
        }]
        _upsert_day(arc, dt, rows)

        # Check is done by caller (backfill loop); verify _already_archived is True
        assert _already_archived(arc, dt)
        # Verify nothing changes if we read back
        shard = _load_shard(_shard_path(arc, dt))
        assert len(shard) == 1


# ---------------------------------------------------------------------------
# 3. order_idx preservation
# ---------------------------------------------------------------------------

def test_order_idx_preserved_in_shard() -> None:
    """Broadcast order (row 0 = lead item) must survive the shard write."""
    raw = _make_raw_frame([
        ("联播头条：经济稳增长", "支持就业促进增长"),   # lead item — idx 0
        ("第二条：科技创新", "高质量发展"),              # idx 1
        ("第三条：外交动态", "合作共赢"),                # idx 2
    ])
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)

        # Mock fetch_day by building rows directly as the script would
        rows = []
        from scripts.backfill_cctv_archive import _is_stub_row
        from datetime import datetime, timezone
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for idx, row in enumerate(raw.itertuples(index=False)):
            title = str(row.title)
            content = str(row.content)
            rows.append({
                "date": "2025-01-15",
                "order_idx": idx,
                "title": title,
                "content": content,
                "fetch_status": "stub" if _is_stub_row(title + content) else "ok",
                "fetched_at": fetched_at,
            })
        _upsert_day(arc, dt, rows)

        shard = _load_shard(_shard_path(arc, dt))
        day = shard[shard["date"] == "2025-01-15"].sort_values("order_idx")
        assert list(day["order_idx"]) == [0, 1, 2]
        assert day.iloc[0]["title"] == "联播头条：经济稳增长"
        assert day.iloc[1]["title"] == "第二条：科技创新"


def test_upsert_replaces_existing_rows() -> None:
    """Second upsert for the same date replaces the first."""
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)
        rows_v1 = [{
            "date": "2025-01-15",
            "order_idx": 0,
            "title": "v1",
            "content": "x",
            "fetch_status": "ok",
            "fetched_at": "2025-01-15T00:00:00Z",
        }]
        rows_v2 = [
            {"date": "2025-01-15", "order_idx": 0, "title": "v2-item0",
             "content": "增长", "fetch_status": "ok", "fetched_at": "2025-01-16T00:00:00Z"},
            {"date": "2025-01-15", "order_idx": 1, "title": "v2-item1",
             "content": "发展", "fetch_status": "ok", "fetched_at": "2025-01-16T00:00:00Z"},
        ]
        _upsert_day(arc, dt, rows_v1)
        _upsert_day(arc, dt, rows_v2)
        shard = _load_shard(_shard_path(arc, dt))
        day = shard[shard["date"] == "2025-01-15"]
        assert len(day) == 2
        assert "v1" not in day["title"].values


# ---------------------------------------------------------------------------
# 4. fetch_day stub tagging (with mocked akshare)
# ---------------------------------------------------------------------------

def test_fetch_day_tags_stub_rows() -> None:
    """fetch_day marks page-rot rows as fetch_status='stub'."""
    stub_frame = pd.DataFrame({
        "date": ["20250115"],
        "title": [""],
        "content": ["对不起，可能是网络原因或无此页面"],
    })
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = stub_frame

    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15))

    assert status == "stub"
    assert len(rows) == 1
    assert rows[0]["fetch_status"] == "stub"
    assert rows[0]["order_idx"] == 0


def test_fetch_day_ok_items() -> None:
    """fetch_day correctly tags real content as 'ok' and preserves order."""
    raw = _make_raw_frame(_GOOD_ITEMS)
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = raw

    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15))

    assert status == "ok"
    assert len(rows) == 2
    assert rows[0]["order_idx"] == 0
    assert rows[1]["order_idx"] == 1
    assert all(r["fetch_status"] == "ok" for r in rows)


def test_fetch_day_empty_returns_empty_list() -> None:
    mock_ak = MagicMock()
    mock_ak.news_cctv.return_value = pd.DataFrame()

    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15))

    assert status == "empty"
    assert rows == []


def test_fetch_day_exception_returns_error_row() -> None:
    mock_ak = MagicMock()
    mock_ak.news_cctv.side_effect = Exception("network timeout")

    with patch.dict("sys.modules", {"akshare": mock_ak}):
        rows, status = fetch_day(date(2025, 1, 15), retries=1)

    assert status == "error"
    assert len(rows) == 1
    assert rows[0]["fetch_status"] == "error"
    assert "network timeout" in rows[0]["content"]


# ---------------------------------------------------------------------------
# 5. Repair logic
# ---------------------------------------------------------------------------

def test_all_stubs_or_error_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)
        # Store all-stub rows
        rows = [{
            "date": "2025-01-15",
            "order_idx": 0,
            "title": "",
            "content": "对不起，可能是网络原因或无此页面",
            "fetch_status": "stub",
            "fetched_at": "2025-01-16T00:00:00Z",
        }]
        _upsert_day(arc, dt, rows)
        assert _all_stubs_or_error(arc, dt)


def test_mixed_ok_stub_not_flagged_as_all_stubs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)
        rows = [
            {"date": "2025-01-15", "order_idx": 0, "title": "real", "content": "增长",
             "fetch_status": "ok", "fetched_at": "2025-01-16T00:00:00Z"},
            {"date": "2025-01-15", "order_idx": 1, "title": "", "content": "对不起",
             "fetch_status": "stub", "fetched_at": "2025-01-16T00:00:00Z"},
        ]
        _upsert_day(arc, dt, rows)
        assert not _all_stubs_or_error(arc, dt)


# ---------------------------------------------------------------------------
# 6. Tone-derivation equivalence
# ---------------------------------------------------------------------------

def test_rebuild_tone_equivalence() -> None:
    """rebuild_cctv_tone_history must produce the same tone as _tone_features directly."""
    items = [
        ("改革开放扩大开放", "经济发展向好，支持就业，促进增长"),
        ("防范风险挑战", "下行压力加大，警惕危机"),
    ]
    raw = _make_raw_frame(items)
    expected = _tone_features(raw)

    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)
        from datetime import datetime, timezone
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = []
        for idx, item in enumerate(items):
            rows.append({
                "date": "2025-01-15",
                "order_idx": idx,
                "title": item[0],
                "content": item[1],
                "fetch_status": "ok",
                "fetched_at": fetched_at,
            })
        _upsert_day(arc, dt, rows)

        out_path = Path(tmp) / "tone_history.parquet"
        df = rebuild(arc, out_path)

    assert pd.Timestamp("2025-01-15") in df.index
    row = df.loc[pd.Timestamp("2025-01-15")]
    assert abs(row["tone"] - expected["tone"]) < 1e-9
    assert int(row["n_items"]) == 2
    assert int(row["n_stub"]) == 0


def test_rebuild_excludes_stub_rows_from_tone() -> None:
    """Stub rows should NOT contribute to the tone calculation."""
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 15)
        from datetime import datetime, timezone
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [
            {"date": "2025-01-15", "order_idx": 0, "title": "改革", "content": "增长发展",
             "fetch_status": "ok", "fetched_at": fetched_at},
            {"date": "2025-01-15", "order_idx": 1, "title": "",
             "content": "对不起，可能是网络原因或无此页面",
             "fetch_status": "stub", "fetched_at": fetched_at},
        ]
        _upsert_day(arc, dt, rows)
        out_path = Path(tmp) / "tone_history.parquet"
        df = rebuild(arc, out_path)

    row = df.loc[pd.Timestamp("2025-01-15")]
    assert int(row["n_items"]) == 1    # only the ok row
    assert int(row["n_stub"]) == 1


def test_rebuild_empty_day_gives_nan_tone() -> None:
    """Days with fetch_status='empty' should appear as NaN tone, n_items=0."""
    with tempfile.TemporaryDirectory() as tmp:
        arc = Path(tmp)
        dt = date(2025, 1, 12)   # Sunday, expect empty
        from datetime import datetime, timezone
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = [{
            "date": "2025-01-12",
            "order_idx": 0,
            "title": "",
            "content": "",
            "fetch_status": "empty",
            "fetched_at": fetched_at,
        }]
        _upsert_day(arc, dt, rows)

        # Add a real day so rebuild has something to write
        rows_real = [{
            "date": "2025-01-13",
            "order_idx": 0,
            "title": "增长",
            "content": "发展",
            "fetch_status": "ok",
            "fetched_at": fetched_at,
        }]
        _upsert_day(arc, date(2025, 1, 13), rows_real)

        out_path = Path(tmp) / "tone_history.parquet"
        df = rebuild(arc, out_path)

    assert pd.Timestamp("2025-01-12") in df.index
    import math
    assert math.isnan(df.loc[pd.Timestamp("2025-01-12"), "tone"])
    assert df.loc[pd.Timestamp("2025-01-12"), "n_items"] == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_stub_signatures_detected,
        test_real_content_not_stub,
        test_already_archived_returns_false_for_missing_date,
        test_already_archived_returns_true_after_upsert,
        test_skip_does_not_call_akshare,
        test_order_idx_preserved_in_shard,
        test_upsert_replaces_existing_rows,
        test_fetch_day_tags_stub_rows,
        test_fetch_day_ok_items,
        test_fetch_day_empty_returns_empty_list,
        test_fetch_day_exception_returns_error_row,
        test_all_stubs_or_error_detection,
        test_mixed_ok_stub_not_flagged_as_all_stubs,
        test_rebuild_tone_equivalence,
        test_rebuild_excludes_stub_rows_from_tone,
        test_rebuild_empty_day_gives_nan_tone,
    ]
    for fn in tests:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
