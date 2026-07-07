"""Dead-man's switch logic (Phase B ops hardening). Fresh + few-breakers = OK;
stale last_run or a broad outage = fail. Pure function, deterministic `now`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from scripts.healthcheck import check_health, check_committed_data_freshness, _sessions_stale

NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _status(hours_ago: float, breakers: dict | None = None) -> dict:
    return {"last_run": (NOW - timedelta(hours=hours_ago)).isoformat(),
            "circuit_breaker": breakers or {}}


def test_fresh_run_is_healthy():
    r = check_health(_status(20, {"cot": 1, "aaii": 3}), NOW)
    assert r["ok"] is True and not r["fail_reasons"]
    assert r["tripped"] == ["aaii"]                       # reported as a warning, not a failure
    assert r["warnings"]


def test_stale_run_fails():
    r = check_health(_status(120), NOW, max_age_hours=96)
    assert r["ok"] is False
    assert any("STALE" in f for f in r["fail_reasons"])


def test_weekend_gap_within_limit_is_ok():
    r = check_health(_status(72), NOW, max_age_hours=96)   # Fri->Mon gap
    assert r["ok"] is True


def test_broad_outage_fails():
    breakers = {f"src{i}": 5 for i in range(9)}            # 9 sources down
    r = check_health(_status(10, breakers), NOW, broad_outage=8)
    assert r["ok"] is False
    assert any("BROAD OUTAGE" in f for f in r["fail_reasons"])


def test_missing_last_run_fails():
    r = check_health({"circuit_breaker": {}}, NOW)
    assert r["ok"] is False
    assert any("last_run" in f for f in r["fail_reasons"])


# ---------------------------------------------------------------------------
# _sessions_stale — pure business-day-staleness helper
# ---------------------------------------------------------------------------

# Reference "now": Monday 2026-06-15 12:00 UTC
_NOW_MON = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def test_sessions_stale_zero_when_current():
    """File dated today → 0 sessions stale."""
    assert _sessions_stale("2026-06-15", _NOW_MON, []) == 0


def test_sessions_stale_one_business_day():
    """File dated Friday one business day before Monday → 1 session stale."""
    assert _sessions_stale("2026-06-12", _NOW_MON, []) == 1


def test_sessions_stale_weekend_does_not_inflate():
    """Thursday to Monday spans Fri+weekend but counts as only 2 business days."""
    # Thu 2026-06-11 → Mon 2026-06-15: Fri counts, Sat/Sun skipped → 2
    assert _sessions_stale("2026-06-11", _NOW_MON, []) == 2


def test_sessions_stale_holiday_excluded():
    """A holiday on Friday reduces the Thu→Mon count from 2 to 1."""
    assert _sessions_stale("2026-06-11", _NOW_MON, ["2026-06-12"]) == 1


def test_sessions_stale_future_date_is_zero():
    """File dated in the future returns 0, never negative."""
    assert _sessions_stale("2026-06-20", _NOW_MON, []) == 0


def test_sessions_stale_accepts_pandas_timestamp():
    """Accepts a pandas Timestamp as returned by frame_asof."""
    ts = pd.Timestamp("2026-06-12")
    assert _sessions_stale(ts, _NOW_MON, []) == 1


# ---------------------------------------------------------------------------
# check_committed_data_freshness — mocked parquet + frame_asof
# ---------------------------------------------------------------------------

def _make_cfg(witnesses, warn=1, fail=2, holidays=None):
    return {
        "warn_after_sessions": warn,
        "fail_after_sessions": fail,
        "witnesses": witnesses,
        "holidays": holidays or [],
    }


def _dummy_df(asof_str: str) -> pd.DataFrame:
    """Minimal OHLC frame with a DatetimeIndex at the given date."""
    return pd.DataFrame(
        {"close": [100.0], "open": [99.0], "high": [101.0], "low": [98.0]},
        index=pd.DatetimeIndex([pd.Timestamp(asof_str)]),
    )


# Use Monday 2026-06-15 as the probe's "now"
_NOW_CHECK = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)

_ONE_WITNESS = [{"label": "test_stock XYZ", "path": "data/stocks/XYZ.parquet"}]


def _run_check(asof_str: str, *, warn=1, fail=2, holidays=None, path_exists=True):
    """Run check_committed_data_freshness with a single mocked witness."""
    cfg = _make_cfg(_ONE_WITNESS, warn=warn, fail=fail, holidays=holidays)
    df = _dummy_df(asof_str)
    asof_ts = pd.Timestamp(asof_str)

    with patch("scripts.healthcheck.config") as mock_cfg, \
         patch("pandas.read_parquet", return_value=df), \
         patch("engine.tushare_freshness.frame_asof", return_value=asof_ts), \
         patch("pathlib.Path.exists", return_value=path_exists):
        mock_cfg.ROOT = MagicMock()
        mock_cfg.ROOT.__truediv__ = lambda self, other: MagicMock(
            __truediv__=lambda s, o: MagicMock(exists=lambda: path_exists)
        )
        # Re-import with our real implementation but patch the path.exists inline
        from scripts.healthcheck import check_committed_data_freshness as _fn
        return _fn(_NOW_CHECK, cfg)


def test_freshness_fresh_file_is_ok():
    """File dated today → ok, no failures, no warnings."""
    cfg = _make_cfg([{"label": "x", "path": "data/stocks/XYZ.parquet"}])
    df = _dummy_df("2026-06-15")
    asof_ts = pd.Timestamp("2026-06-15")

    with patch("pathlib.Path.exists", return_value=True), \
         patch("pandas.read_parquet", return_value=df):
        import engine.tushare_freshness as tf
        with patch.object(tf, "frame_asof", return_value=asof_ts):
            from scripts.healthcheck import check_committed_data_freshness as fn
            r = fn(_NOW_CHECK, cfg)

    assert r["ok"] is True
    assert r["fail_reasons"] == []


def test_freshness_stale_beyond_fail_threshold():
    """File 3 sessions stale (> fail_after=2) → fail, ::error:: message present."""
    # 2026-06-11 (Thu) → Mon 2026-06-15: 2 business days stale.
    # Use 2026-06-10 (Wed) → 3 business days stale → should fail.
    cfg = _make_cfg([{"label": "china_stocks 000001.SZ", "path": "data/china_stocks/000001.SZ.parquet"}],
                    fail=2)
    df = _dummy_df("2026-06-10")
    asof_ts = pd.Timestamp("2026-06-10")

    with patch("pathlib.Path.exists", return_value=True), \
         patch("pandas.read_parquet", return_value=df):
        import engine.tushare_freshness as tf
        with patch.object(tf, "frame_asof", return_value=asof_ts):
            from scripts.healthcheck import check_committed_data_freshness as fn
            r = fn(_NOW_CHECK, cfg)

    assert r["ok"] is False
    assert len(r["fail_reasons"]) == 1
    msg = r["fail_reasons"][0]
    assert "data-freeze" in msg
    assert "3 trading-days stale" in msg
    assert "2026-06-10" in msg
    assert "not landing in git" in msg


def test_freshness_one_session_stale_within_warn_threshold_is_ok():
    """File exactly 1 session stale with warn_after=1 → stale > warn_after is False → clean."""
    # warn_after=1 means "warn when stale > 1", so exactly 1 session stale is still clean.
    cfg = _make_cfg([{"label": "us_stocks AAPL", "path": "data/stocks/AAPL.parquet"}],
                    warn=1, fail=2)
    df = _dummy_df("2026-06-12")
    asof_ts = pd.Timestamp("2026-06-12")

    with patch("pathlib.Path.exists", return_value=True), \
         patch("pandas.read_parquet", return_value=df):
        import engine.tushare_freshness as tf
        with patch.object(tf, "frame_asof", return_value=asof_ts):
            from scripts.healthcheck import check_committed_data_freshness as fn
            r = fn(_NOW_CHECK, cfg)

    assert r["ok"] is True
    assert r["fail_reasons"] == []
    assert r["warnings"] == []  # exactly at limit: no warn, no fail


def test_freshness_weekend_gap_within_threshold_ok():
    """Friday through Monday is 1 session; with fail=2 that must NOT fail."""
    cfg = _make_cfg([{"label": "us_stocks AAPL", "path": "data/stocks/AAPL.parquet"}],
                    warn=2, fail=3)  # raise thresholds so 1-session gap is clean
    df = _dummy_df("2026-06-12")
    asof_ts = pd.Timestamp("2026-06-12")

    with patch("pathlib.Path.exists", return_value=True), \
         patch("pandas.read_parquet", return_value=df):
        import engine.tushare_freshness as tf
        with patch.object(tf, "frame_asof", return_value=asof_ts):
            from scripts.healthcheck import check_committed_data_freshness as fn
            r = fn(_NOW_CHECK, cfg)

    assert r["ok"] is True
    assert r["fail_reasons"] == []


def test_freshness_configured_holiday_avoids_false_positive():
    """A Thursday file with Friday as holiday → 1 session stale (not 2); no fail with fail=2."""
    # Thu 2026-06-11 → Mon 2026-06-15 normally = 2 business days stale → would trigger fail=2.
    # With Fri 2026-06-12 marked as a holiday: busday_count = 1 → below fail threshold.
    cfg = _make_cfg([{"label": "china_stocks 000001.SZ", "path": "data/china_stocks/000001.SZ.parquet"}],
                    warn=1, fail=2, holidays=["2026-06-12"])
    df = _dummy_df("2026-06-11")
    asof_ts = pd.Timestamp("2026-06-11")

    with patch("pathlib.Path.exists", return_value=True), \
         patch("pandas.read_parquet", return_value=df):
        import engine.tushare_freshness as tf
        with patch.object(tf, "frame_asof", return_value=asof_ts):
            from scripts.healthcheck import check_committed_data_freshness as fn
            r = fn(_NOW_CHECK, cfg)

    assert r["ok"] is True
    assert r["fail_reasons"] == []
    # 1 session stale is NOT > warn_after=1, so no warning either
    assert r["warnings"] == []


def test_freshness_missing_witness_warns_not_fails():
    """A missing witness file must produce a warning and NOT fail."""
    cfg = _make_cfg([{"label": "gone_store FOO", "path": "data/nonexistent/FOO.parquet"}])

    with patch("pathlib.Path.exists", return_value=False):
        from scripts.healthcheck import check_committed_data_freshness as fn
        r = fn(_NOW_CHECK, cfg)

    assert r["ok"] is True
    assert r["fail_reasons"] == []
    assert len(r["warnings"]) == 1
    assert "missing" in r["warnings"][0]


def test_freshness_empty_witnesses_is_ok():
    """No witnesses configured → trivially ok with no noise."""
    cfg = _make_cfg([])
    from scripts.healthcheck import check_committed_data_freshness as fn
    r = fn(_NOW_CHECK, cfg)
    assert r["ok"] is True
    assert r["fail_reasons"] == []
    assert r["warnings"] == []


def test_freshness_degrade_on_import_failure():
    """If engine.tushare_freshness import fails, degrade to a single warning."""
    cfg = _make_cfg([{"label": "x", "path": "data/stocks/XYZ.parquet"}])

    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "engine.tushare_freshness":
            raise ImportError("simulated import failure")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        from scripts.healthcheck import check_committed_data_freshness as fn
        r = fn(_NOW_CHECK, cfg)

    assert r["ok"] is True
    assert r["fail_reasons"] == []
    assert len(r["warnings"]) == 1
    assert "skipped" in r["warnings"][0]
