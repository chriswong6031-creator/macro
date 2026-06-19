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
        seen["period"] = period                                  # last call (back-compat)
        seen.setdefault("calls", []).append((period, list(batch)))
        return _fake_frame(list(batch))

    monkeypatch.setattr(ip.yf, "download", fake_download)
    return ip.IntlPriceAdapter(), seen


def _seed_all_configured(adapter: ip.IntlPriceAdapter, grp: Path) -> list[str]:
    """Write a parquet for every configured ticker so the store is fully warm
    (no 'new' series). Returns the raw ticker list."""
    grp.mkdir(parents=True, exist_ok=True)
    core, optional = adapter._ticker_sets()
    tickers = core + optional
    for t in tickers:
        _fake_frame([t]).to_parquet(grp / f"{ip.IntlPriceAdapter._safe(t)}.parquet")
    return tickers


def test_cold_store_seeds_full_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)  # empty -> cold
    adapter, seen = _adapter_capturing(monkeypatch)

    frames = adapter.fetch(full_history=False)

    assert seen["period"] == "max", "cold store must backfill deep history"
    assert frames, "expected seeded frames"


def test_warm_store_uses_incremental(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    adapter, seen = _adapter_capturing(monkeypatch)
    # warm AND complete: every configured ticker already stored -> no 'new' series,
    # so the whole plane uses the 1mo daily incremental window (never 'max').
    _seed_all_configured(adapter, tmp_path / "intl")
    adapter.fetch(full_history=False)

    assert all(p == "1mo" for p, _ in seen["calls"]), "fully-warm store must use 1mo only"


def test_new_series_on_warm_store_seeds_full_history(tmp_path, monkeypatch):
    """A market added to config on an already-warm store must DEEP-seed only the
    new index/FX series — 1mo is too shallow for the regime engine. The previously
    stored tickers stay on the cheap incremental window."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    adapter, seen = _adapter_capturing(monkeypatch)
    grp = tmp_path / "intl"
    tickers = _seed_all_configured(adapter, grp)
    # simulate a freshly-added market: drop one core series from the warm store
    fresh = "^AXJO" if "^AXJO" in tickers else tickers[0]
    (grp / f"{ip.IntlPriceAdapter._safe(fresh)}.parquet").unlink()

    adapter.fetch(full_history=False)

    max_batches = [b for p, b in seen["calls"] if p == "max"]
    incr_batches = [b for p, b in seen["calls"] if p == "1mo"]
    assert max_batches, "the new series must trigger a deep (max) backfill"
    assert all(fresh in b for b in max_batches), "only the new series is deep-seeded at max"
    assert sum(len(b) for b in max_batches) == 1, "exactly one new series, deep-seeded"
    assert any("^N225" in b for b in incr_batches), "already-stored series stay incremental"


def test_full_history_flag_forces_max_even_when_warm(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    grp = tmp_path / "intl"
    grp.mkdir(parents=True)
    _fake_frame(["^N225"]).to_parquet(grp / "_N225.parquet")

    adapter, seen = _adapter_capturing(monkeypatch)
    adapter.fetch(full_history=True)

    assert seen["period"] == "max"
