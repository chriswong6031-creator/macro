from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import build_intraday_flow as bif
from scripts.build_intraday_flow_quotes import build_payload


def test_board_quote_filter_keeps_only_leaders_with_real_prices():
    payload = build_payload(
        {"leaders": [{"ticker": "AMD"}, {"ticker": "AAPL"}, {"ticker": "MISS"}]},
        {
            "ts": 123,
            "asof": "2026-08-20T16:00:00+00:00",
            "source": "snapshot",
            "quotes": {
                "AAPL": {"price": 200.0},
                "AMD": {"price": "150.25"},
                "MISS": {"price": None},
                "SPY": {"price": 700.0},
            },
            "meta": {"requested": 2000, "resolved": 1900},
        },
    )
    assert set(payload["quotes"]) == {"AAPL", "AMD"}
    assert payload["meta"]["requested"] == 3
    assert payload["meta"]["resolved"] == 2
    assert payload["meta"]["upstream_resolved"] == 1900


def test_datetime_index_named_ts_is_normalized_for_today_bars(
    monkeypatch, tmp_path: Path
):
    now_et = pd.Timestamp.now(tz="America/New_York").normalize()
    index = pd.DatetimeIndex(
        [now_et + pd.Timedelta(hours=10), now_et + pd.Timedelta(hours=11)],
        name="ts",
    ).tz_convert("UTC")
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000.0, 2000.0],
        },
        index=index,
    )
    intraday = tmp_path / "intraday"
    intraday.mkdir()
    (intraday / "AAPL.parquet").touch()
    monkeypatch.setattr(bif.pd, "read_parquet", lambda _: frame.copy())

    rows = bif._today_bars("AAPL", tmp_path)

    assert len(rows) == 2
    assert rows[-1]["close"] == 102.0
