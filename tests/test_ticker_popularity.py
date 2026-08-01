from __future__ import annotations

from pathlib import Path

import pandas as pd

from lib import config
from lib.ticker_popularity import (
    attach_latest_volume,
    latest_volume_map,
)


ROOT = Path(__file__).resolve().parents[1]


def test_latest_volume_map_reads_latest_completed_deep_session(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    stocks = tmp_path / "stocks"
    stocks.mkdir()
    pd.DataFrame(
        {"volume": [100.0, 350.0]},
        index=pd.to_datetime(["2026-07-28", "2026-07-29"]),
    ).to_parquet(stocks / "AAA.parquet")
    pd.DataFrame(
        {"volume": [900.0, None]},
        index=pd.to_datetime(["2026-07-28", "2026-07-29"]),
    ).to_parquet(stocks / "BBB.parquet")

    latest_volume_map.cache_clear()
    assert latest_volume_map("us") == {"AAA": 350, "BBB": 900}


def test_members_snapshot_supplies_canada_and_international_volume(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    members_dir = tmp_path / "canada_search"
    members_dir.mkdir()
    pd.DataFrame(
        {"name": ["Alpha", "Beta"], "volume": [1_250_000.0, None]},
        index=["AAA.TO", "BBB.TO"],
    ).to_parquet(members_dir / "members.parquet")

    latest_volume_map.cache_clear()
    assert latest_volume_map("ca") == {"AAA.TO": 1_250_000}


def test_index_volume_field_is_compact_and_display_only() -> None:
    row = {"t": "AAA", "n": "Alpha"}
    attach_latest_volume(row, "AAA", {"AAA": 123_456})
    assert row == {"t": "AAA", "n": "Alpha", "v": 123_456}

    for name, market in (
        ("build_stock_library.py", "us"),
        ("build_china_library.py", "cn"),
        ("build_hk_library.py", "hk"),
        ("build_canada_library.py", "ca"),
        ("build_intl_library.py", "intl"),
    ):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert f'latest_volume_map("{market}")' in source
        assert "attach_latest_volume(idx, ticker, latest_volumes)" in source


def test_search_collectors_retain_volume_from_existing_yfinance_download() -> None:
    for name in ("canada_universe.py", "intl_universe.py"):
        source = (ROOT / "collectors" / name).read_text(encoding="utf-8")
        assert 'df["Volume"]' in source
        assert 'members["volume"]' in source
        assert "latest-volume" not in source  # no second network request/lane
