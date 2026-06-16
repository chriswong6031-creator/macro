"""Cold-start auto-seed for the international price plane.

Regression for the bug that left /intl.html un-deployable: the daily collector
fetches period='1mo', but a fresh deploy has an EMPTY `intl` store, and ~1 month of
index data is too shallow for the regime engine (every country_record() comes back
empty -> build_intl skips the page). The collector must backfill DEEP history when
the store is cold, then fall back to the 1mo incremental once seeded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors import intl_prices as ip  # noqa: E402
from lib import config  # noqa: E402


def _fake_frame(batch: list[str]) -> pd.DataFrame:
    """yfinance group_by='ticker' shape: columns = MultiIndex(ticker, field)."""
    idx = pd.date_range("2018-01-01", periods=120, freq="B")
    cols = pd.MultiIndex.from_product([batch, ["Open", "High", "Low", "Close", "Volume"]])
    data = [[100.0] * len(cols) for _ in idx]
    return pd.DataFrame(data, index=idx, columns=cols)


def _adapter_capturing(monkeypatch) -> tuple[ip.IntlPriceAdapter, dict]:
    seen: dict = {}

    def fake_download(batch, period, **kw):  # noqa: ANN001
        seen["period"] = period
        return _fake_frame(list(batch))

    monkeypatch.setattr(ip.yf, "download", fake_download)
    return ip.IntlPriceAdapter(), seen


def test_cold_store_seeds_full_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)  # empty -> cold
    adapter, seen = _adapter_capturing(monkeypatch)

    frames = adapter.fetch(full_history=False)

    assert seen["period"] == "max", "cold store must backfill deep history"
    assert frames, "expected seeded frames"


def test_warm_store_uses_incremental(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    # warm: at least one parquet already in the group dir
    grp = tmp_path / "intl"
    grp.mkdir(parents=True)
    _fake_frame(["^N225"]).to_parquet(grp / "_N225.parquet")

    adapter, seen = _adapter_capturing(monkeypatch)
    adapter.fetch(full_history=False)

    assert seen["period"] == "1mo", "warm store must use the daily incremental window"


def test_full_history_flag_forces_max_even_when_warm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    grp = tmp_path / "intl"
    grp.mkdir(parents=True)
    _fake_frame(["^N225"]).to_parquet(grp / "_N225.parquet")

    adapter, seen = _adapter_capturing(monkeypatch)
    adapter.fetch(full_history=True)

    assert seen["period"] == "max"
