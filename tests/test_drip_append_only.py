"""Append-only PIT drip caches (CN-1 masterplan §W6-CN).

The zt_pool / margin_detail / LHB caches used to snapshot-overwrite (one date on disk). They are now
APPEND-ONLY, keyed by their natural PIT date, so the point-in-time record survives for pinned-entry
flags and a future 连板 veto. This pins:
  • collectors/_drip.append_snapshot grows a multi-date history, keep-last per (date, ticker);
  • collectors/_drip.latest_snapshot returns exactly the newest-date slice;
  • the engine consumers (china_extras) still see a single-day per-ticker snapshot after the store
    grows a second date — i.e. no double-counting across dates.
"""
import pandas as pd
import pytest

from lib import config
from collectors import _drip


def test_append_snapshot_is_append_only_keep_last(tmp_path):
    p = tmp_path / "pool.parquet"
    _drip.append_snapshot(p, [{"date": "2026-06-30", "ticker": "A", "v": 1},
                              {"date": "2026-06-30", "ticker": "B", "v": 2}], "date")
    _drip.append_snapshot(p, [{"date": "2026-07-01", "ticker": "A", "v": 10}], "date")
    full = pd.read_parquet(p)
    assert sorted(full["date"].unique()) == ["2026-06-30", "2026-07-01"]   # history retained
    # a same-day re-collect CORRECTS, never duplicates
    n = _drip.append_snapshot(p, [{"date": "2026-07-01", "ticker": "A", "v": 99}], "date")
    full = pd.read_parquet(p)
    assert len(full[full["date"] == "2026-07-01"]) == 1                    # no dup
    assert full[(full["date"] == "2026-07-01") & (full["ticker"] == "A")]["v"].iloc[0] == 99
    assert n == 1                                                         # latest-day row count


def test_latest_snapshot_returns_newest_day(tmp_path):
    df = pd.DataFrame({"date": ["2026-06-30", "2026-07-01", "2026-07-01"],
                       "ticker": ["A", "A", "B"], "v": [1, 10, 20]})
    latest = _drip.latest_snapshot(df, "date")
    assert set(latest["date"]) == {"2026-07-01"} and len(latest) == 2


def test_latest_snapshot_passthrough_when_no_date_col():
    df = pd.DataFrame({"ticker": ["A"], "v": [1]})
    assert _drip.latest_snapshot(df, "date") is df                        # older schema untouched


def test_zt_pool_consumer_sees_only_latest_session(tmp_path, monkeypatch):
    """A two-session zt_pool history must render as ONE session to china_extras.zt_pool (no double)."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    from engine import china_extras
    rows = []
    for d, consec in (("2026-06-30", 2), ("2026-07-01", 5)):
        rows += [{"ticker": "600000.SS", "name": "x", "consec_boards": consec,
                  "seal_fund_yi": 1.0, "failed_seals": 0, "turnover_pct": 10.0,
                  "sector": "s", "date": d, "asof": d}]
    _drip.append_snapshot(tmp_path / "china_zt_pool" / "pool.parquet", rows, "date")
    out = china_extras.zt_pool()
    assert set(out) == {"600000.SS"}                                     # one row, not two
    assert out["600000.SS"]["consec_boards"] == 5                        # the LATEST session's value


def test_margin_consumer_sees_only_latest_session(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    from engine import china_extras
    rows = [{"ticker": "600000.SS", "fin_balance": 100.0, "fin_balance_prior": 90.0,
             "date": "2026-06-30", "prior_date": "2026-06-01", "asof": "2026-06-30"},
            {"ticker": "600000.SS", "fin_balance": 200.0, "fin_balance_prior": 100.0,
             "date": "2026-07-01", "prior_date": "2026-06-02", "asof": "2026-07-01"}]
    _drip.append_snapshot(tmp_path / "china_margin_detail" / "detail.parquet", rows, "date")
    out = china_extras.margin_positioning({"600000.SS": 1000.0})
    assert set(out) == {"600000.SS"}                                     # single latest row
