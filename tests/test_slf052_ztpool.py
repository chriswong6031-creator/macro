"""Tests for china_zt_pool collector logic — SLF-052.

Pure-function tests; NO network, NO disk I/O beyond tiny in-memory fixtures.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

# ── _drip helpers ─────────────────────────────────────────────────────────────

from collectors._drip import append_snapshot, latest_snapshot


def _tmp_path(tmp_path, name="pool.parquet"):
    return tmp_path / name


def test_latest_snapshot_returns_newest_date():
    df = pd.DataFrame({
        "date": ["2026-06-15", "2026-06-15", "2026-06-16", "2026-06-16"],
        "ticker": ["A.SZ", "B.SZ", "A.SZ", "B.SZ"],
        "value": [1, 2, 3, 4],
    })
    result = latest_snapshot(df, "date")
    assert list(result["date"].unique()) == ["2026-06-16"]
    assert len(result) == 2


def test_latest_snapshot_passthrough_on_missing_col():
    df = pd.DataFrame({"ticker": ["A", "B"]})
    result = latest_snapshot(df, "date")
    assert result is df


def test_append_snapshot_creates_file(tmp_path):
    path = _tmp_path(tmp_path)
    rows = [
        {"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 1},
        {"ticker": "000002.SZ", "date": "2026-06-15", "consec_boards": 2},
    ]
    n = append_snapshot(path, rows, date_col="date")
    assert n == 2
    df = pd.read_parquet(path)
    assert len(df) == 2


def test_append_snapshot_idempotent_same_day(tmp_path):
    """Re-appending the same session rows must not duplicate."""
    path = _tmp_path(tmp_path)
    rows = [{"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 1}]
    append_snapshot(path, rows, date_col="date")
    append_snapshot(path, rows, date_col="date")  # second time — same session
    df = pd.read_parquet(path)
    assert len(df) == 1


def test_append_snapshot_corrects_same_day(tmp_path):
    """A same-day re-collect with updated data must correct, not duplicate."""
    path = _tmp_path(tmp_path)
    rows_v1 = [{"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 1}]
    rows_v2 = [{"ticker": "000001.SZ", "date": "2026-06-15", "consec_boards": 3}]
    append_snapshot(path, rows_v1, date_col="date")
    append_snapshot(path, rows_v2, date_col="date")
    df = pd.read_parquet(path)
    assert len(df) == 1
    assert int(df.iloc[0]["consec_boards"]) == 3


def test_append_snapshot_accumulates_sessions(tmp_path):
    """Different session dates accumulate correctly."""
    path = _tmp_path(tmp_path)
    for date in ["2026-06-15", "2026-06-16", "2026-06-17"]:
        rows = [
            {"ticker": "000001.SZ", "date": date, "consec_boards": 1},
            {"ticker": "000002.SZ", "date": date, "consec_boards": 1},
        ]
        append_snapshot(path, rows, date_col="date")
    df = pd.read_parquet(path)
    assert len(df) == 6  # 3 sessions × 2 tickers
    assert sorted(df["date"].unique()) == ["2026-06-15", "2026-06-16", "2026-06-17"]


# ── collector _parse logic ─────────────────────────────────────────────────────

from collectors.china_zt_pool import _parse, _col, _stored_sessions


def _raw_pool(turnover: float = 5.0) -> pd.DataFrame:
    return pd.DataFrame({
        "代码": ["000001", "600001"],
        "名称": ["A公司", "B公司"],
        "连板数": [2, 1],
        "封板资金": [5e8, 1e8],
        "炸板次数": [0, 1],
        "换手率": [turnover, 3.0],
        "所属行业": ["银行", "科技"],
    })


def _write_reference(path, sessions: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {"close": range(len(sessions))}, index=pd.DatetimeIndex(sessions, name="Date")
    ).to_parquet(path)


def test_col_returns_first_match():
    cols = ["代码", "名称", "连板数", "封板资金"]
    assert _col(cols, "代码") == "代码"
    assert _col(cols, "连板") == "连板数"
    assert _col(cols, "missing") is None


def test_parse_basic():
    df = _raw_pool()
    rows = _parse("20260615", df, "2026-06-15")
    assert len(rows) == 2
    # SH/SZ routing
    tickers = {r["ticker"] for r in rows}
    assert "000001.SZ" in tickers
    assert "600001.SS" in tickers  # Shanghai suffix is .SS per china_analyst.to_ticker
    # date field is ISO
    assert all(r["date"] == "2026-06-15" for r in rows)
    # seal_fund_yi conversion
    b_row = next(r for r in rows if r["ticker"] == "600001.SS")
    assert abs(b_row["seal_fund_yi"] - 1.0) < 0.01


def test_parse_empty_df_returns_empty():
    df = pd.DataFrame(columns=["代码", "名称"])
    rows = _parse("20260615", df, "2026-06-15")
    assert rows == []


def test_stored_sessions_empty_on_nonexistent(tmp_path, monkeypatch):
    """_stored_sessions returns empty set when file missing."""
    import collectors.china_zt_pool as mod
    original_out = mod.OUT
    mod.OUT = tmp_path / "nonexistent.parquet"
    try:
        result = mod._stored_sessions()
        assert result == set()
    finally:
        mod.OUT = original_out


# ── observed-session and stale-payload guards ──────────────────────────────────


def test_observed_sessions_fail_closed_when_reference_missing_or_stale(tmp_path, monkeypatch):
    import collectors.china_zt_pool as mod

    missing = tmp_path / "missing.parquet"
    monkeypatch.setattr(mod, "SESSION_REF", missing)
    with pytest.raises(mod.SessionReferenceError, match="missing"):
        mod._load_observed_sessions(required_through=date(2026, 8, 7))

    _write_reference(missing, ["2026-08-06"])
    with pytest.raises(mod.SessionReferenceError, match="stale"):
        mod._load_observed_sessions(required_through=date(2026, 8, 7))


def test_refresh_on_weekend_fetches_and_stamps_friday_only(tmp_path, monkeypatch):
    import collectors.china_zt_pool as mod

    ref = tmp_path / "china" / "000001.SS.parquet"
    out = tmp_path / "china_zt_pool" / "pool.parquet"
    _write_reference(ref, ["2026-08-03", "2026-08-04", "2026-08-05",
                           "2026-08-06", "2026-08-07"])
    calls: list[str] = []

    def fake_pool(day: str):
        calls.append(day)
        return _raw_pool()

    monkeypatch.setattr(mod, "SESSION_REF", ref)
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod, "_pool_for", fake_pool)
    monkeypatch.setattr(mod.cn_calendar, "expected_last_session", lambda _now: date(2026, 8, 7))

    n = mod.refresh(datetime(2026, 8, 8, 12, tzinfo=timezone.utc))
    assert n == 2
    assert calls == ["20260807"]
    stored = pd.read_parquet(out)
    assert set(stored["date"]) == {"2026-08-07"}

    # Per-session idempotency: a second weekend run neither fetches nor writes a Saturday row.
    calls.clear()
    assert mod.refresh(datetime(2026, 8, 8, 20, tzinfo=timezone.utc)) == 0
    assert calls == []
    assert set(pd.read_parquet(out)["date"]) == {"2026-08-07"}


def test_refresh_rejects_exact_replay_of_prior_session(tmp_path, monkeypatch):
    import collectors.china_zt_pool as mod

    ref = tmp_path / "china" / "000001.SS.parquet"
    out = tmp_path / "china_zt_pool" / "pool.parquet"
    _write_reference(ref, ["2026-08-07", "2026-08-10"])
    append_snapshot(out, _parse("20260807", _raw_pool(), "2026-08-07"), date_col="date")
    calls: list[str] = []

    def stale_pool(day: str):
        calls.append(day)
        return _raw_pool()  # Eastmoney replay: Monday payload is exactly Friday's economics.

    monkeypatch.setattr(mod, "SESSION_REF", ref)
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod, "_pool_for", stale_pool)
    monkeypatch.setattr(mod.cn_calendar, "expected_last_session", lambda _now: date(2026, 8, 10))

    assert mod.refresh(datetime(2026, 8, 10, 12, tzinfo=timezone.utc)) == 0
    assert calls == ["20260810"]
    assert set(pd.read_parquet(out)["date"]) == {"2026-08-07"}


def test_clone_guard_accepts_same_names_when_any_semantic_value_changes():
    import collectors.china_zt_pool as mod

    friday = pd.DataFrame(_parse("20260807", _raw_pool(), "2026-08-07"))
    monday = _parse("20260810", _raw_pool(turnover=5.1), "2026-08-10")
    assert mod._exact_prior_clone("2026-08-10", monday, friday) is None


def test_backfill_requests_only_observed_sessions_not_holiday_or_weekend(tmp_path, monkeypatch):
    import collectors.china_zt_pool as mod

    ref = tmp_path / "china" / "000001.SS.parquet"
    out = tmp_path / "china_zt_pool" / "pool.parquet"
    # 2026-06-19 is Dragon Boat; 20/21 are weekend.  The observed index jumps 18 -> 22.
    _write_reference(ref, ["2026-06-18", "2026-06-22"])
    calls: list[str] = []

    def fake_pool(day: str):
        calls.append(day)
        return _raw_pool(turnover=5.0 if day == "20260618" else 5.1)

    monkeypatch.setattr(mod, "SESSION_REF", ref)
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod, "_pool_for", fake_pool)

    assert mod.backfill("2026-06-18", "2026-06-22") == 2
    assert calls == ["20260618", "20260622"]
    assert set(pd.read_parquet(out)["date"]) == {"2026-06-18", "2026-06-22"}


# ── explicit one-time history repair ───────────────────────────────────────────


def test_explicit_repair_removes_only_exact_manifest_clones_atomically(tmp_path, monkeypatch):
    import collectors.china_zt_pool as mod

    ref = tmp_path / "china" / "000001.SS.parquet"
    out = tmp_path / "china_zt_pool" / "pool.parquet"
    _write_reference(ref, ["2026-07-03", "2026-07-06"])
    friday = _parse("20260703", _raw_pool(), "2026-07-03")
    saturday = [dict(r, date="2026-07-04", asof="2026-07-04") for r in friday]
    sunday = [dict(r, date="2026-07-05", asof="2026-07-05") for r in friday]
    monday = _parse("20260706", _raw_pool(turnover=5.1), "2026-07-06")
    out.parent.mkdir(parents=True)
    pd.DataFrame(friday + saturday + sunday + monday).to_parquet(out, index=False)

    real_replace = mod.os.replace
    replacements: list[tuple[object, object]] = []

    def recording_replace(src, dst):
        replacements.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(mod, "SESSION_REF", ref)
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod.os, "replace", recording_replace)

    assert mod.repair_off_session_clones() == 4
    assert len(replacements) == 1
    repaired = pd.read_parquet(out)
    assert set(repaired["date"]) == {"2026-07-03", "2026-07-06"}
    assert mod.repair_off_session_clones() == 0
    assert len(replacements) == 1


def test_repair_retains_unmanifested_off_session_even_when_exact_clone(tmp_path, monkeypatch):
    import collectors.china_zt_pool as mod

    ref = tmp_path / "china" / "000001.SS.parquet"
    out = tmp_path / "china_zt_pool" / "pool.parquet"
    _write_reference(ref, ["2026-08-07"])
    friday = _parse("20260807", _raw_pool(), "2026-08-07")
    sunday = [dict(r, date="2026-08-09", asof="2026-08-09") for r in friday]
    out.parent.mkdir(parents=True)
    pd.DataFrame(friday + sunday).to_parquet(out, index=False)
    before = out.read_bytes()
    monkeypatch.setattr(mod, "SESSION_REF", ref)
    monkeypatch.setattr(mod, "OUT", out)

    assert mod.repair_off_session_clones() == 0
    assert out.read_bytes() == before
    assert set(pd.read_parquet(out)["date"]) == {"2026-08-07", "2026-08-09"}


def test_repair_missing_reference_fails_without_touching_history(tmp_path, monkeypatch):
    import collectors.china_zt_pool as mod

    out = tmp_path / "china_zt_pool" / "pool.parquet"
    out.parent.mkdir(parents=True)
    friday = _parse("20260807", _raw_pool(), "2026-08-07")
    saturday = [dict(r, date="2026-08-08", asof="2026-08-08") for r in friday]
    pd.DataFrame(friday + saturday).to_parquet(out, index=False)
    before = out.read_bytes()
    monkeypatch.setattr(mod, "SESSION_REF", tmp_path / "missing.parquet")
    monkeypatch.setattr(mod, "OUT", out)

    with pytest.raises(mod.SessionReferenceError, match="missing"):
        mod.repair_off_session_clones()
    assert out.read_bytes() == before
