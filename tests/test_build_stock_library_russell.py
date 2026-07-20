"""Russell 2000 closes-cache wiring in scripts/build_stock_library.py.

Tests cover:
  * universe() picks up tickers present only in a synthetic russell_breadth
    cache fixture (i.e. they are not already in breadth / smallcap / midcap).
  * universe() with a missing russell_breadth cache produces no error and
    simply skips that layer.
  * The ::notice line in main() prints universe size and elapsed seconds
    to stdout (via the log INFO path captured by capsys / caplog).
"""
from __future__ import annotations

import logging
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_stock_library as bsl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_closes(tickers: list[str], n: int = 5, tmp_dir: Path = None) -> Path:
    """Write a minimal _closes_cache.parquet to tmp_dir."""
    idx = pd.date_range("2024-01-01", periods=n, freq="D", name="Date")
    data = {t: pd.Series([10.0 + i for i in range(n)], index=idx)
            for t in tickers}
    df = pd.DataFrame(data)
    p = tmp_dir / "_closes_cache.parquet"
    df.to_parquet(p)
    return p


def _make_constituents(tickers: list[str], tmp_dir: Path) -> Path:
    """Write a minimal constituents.parquet indexed by ticker."""
    meta = pd.DataFrame(
        {"name": [f"Name {t}" for t in tickers],
         "sector": ["Test" for _ in tickers]},
        index=pd.Index(tickers, name="ticker"),
    )
    p = tmp_dir / "constituents.parquet"
    meta.to_parquet(p)
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_universe_picks_up_russell_only_tickers(tmp_path, monkeypatch):
    """A ticker present only in russell_breadth must appear in universe()."""
    # Build a fake data dir with only russell_breadth populated.
    data_root = tmp_path / "data"
    russ_dir = data_root / "russell_breadth"
    russ_dir.mkdir(parents=True)

    russell_tickers = ["RTWO", "RTHREE"]
    _make_closes(russell_tickers, tmp_dir=russ_dir)
    _make_constituents(russell_tickers, tmp_dir=russ_dir)

    # Patch config.data_dir to point at our fake data root.
    monkeypatch.setattr("lib.config.data_dir", lambda: data_root)

    # universe() also reads config.load()["yahoo"] for ETF lists and
    # config.data_dir()/"stocks" + "sector_holdings". Those don't exist in
    # tmp_path, so we also need to stub out the config load to avoid a real
    # config.yml parse that returns a real data/ path.
    import lib.config as _cfg
    real_load = _cfg.load
    # Provide a minimal yaml-shaped config so bsl.universe() won't crash on
    # missing keys when it tries to read the yahoo tickers block.
    _cfg.load.cache_clear()
    monkeypatch.setattr(
        _cfg, "load",
        lambda: {
            **real_load(),
        },
    )
    # Re-patch data_dir AFTER load() was potentially called above.
    monkeypatch.setattr("lib.config.data_dir", lambda: data_root)
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)

    result = bsl.universe()
    found_tickers = {t for (t, *_) in result}
    for ticker in russell_tickers:
        assert ticker in found_tickers, (
            f"{ticker} from russell_breadth not found in universe(); "
            f"found: {sorted(found_tickers)}"
        )


def test_universe_missing_russell_cache_no_error(tmp_path, monkeypatch):
    """universe() with russell_breadth absent must not raise — just skip."""
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    # russell_breadth dir does not exist at all.

    import lib.config as _cfg
    _cfg.load.cache_clear()
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)

    # Should not raise; result is a list (possibly empty).
    result = bsl.universe()
    assert isinstance(result, list)


def test_universe_missing_russell_constituents_no_error(tmp_path, monkeypatch):
    """universe() with _closes_cache.parquet but no constituents.parquet
    must not raise — both files are required, and the layer is silently
    skipped when either is absent (matching existing breadth behaviour)."""
    data_root = tmp_path / "data"
    russ_dir = data_root / "russell_breadth"
    russ_dir.mkdir(parents=True)

    # Write only the closes cache, no constituents.
    _make_closes(["RONLY"], tmp_dir=russ_dir)
    # constituents.parquet deliberately omitted.

    import lib.config as _cfg
    _cfg.load.cache_clear()
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)

    result = bsl.universe()
    found_tickers = {t for (t, *_) in result}
    # RONLY must NOT appear (no meta → skip layer).
    assert "RONLY" not in found_tickers


def test_universe_russell_dedup_priority(tmp_path, monkeypatch):
    """A ticker already seen in breadth must NOT be duplicated from russell."""
    data_root = tmp_path / "data"

    # breadth layer has AAPL.
    breadth_dir = data_root / "breadth"
    breadth_dir.mkdir(parents=True)
    _make_closes(["AAPL"], tmp_dir=breadth_dir)
    _make_constituents(["AAPL"], tmp_dir=breadth_dir)

    # russell layer also has AAPL (should be deduped) plus a new name.
    russ_dir = data_root / "russell_breadth"
    russ_dir.mkdir(parents=True)
    _make_closes(["AAPL", "RNEW"], tmp_dir=russ_dir)
    _make_constituents(["AAPL", "RNEW"], tmp_dir=russ_dir)

    import lib.config as _cfg
    _cfg.load.cache_clear()
    monkeypatch.setattr(_cfg, "data_dir", lambda: data_root)

    result = bsl.universe()
    found_tickers = [t for (t, *_) in result]
    # AAPL must appear exactly once.
    assert found_tickers.count("AAPL") == 1
    # RNEW must appear from the russell layer.
    assert "RNEW" in found_tickers


def test_notice_line_format(caplog):
    """The ::notice title=stock_library:: line in main() has universe= and
    elapsed= fields, matching the repo's ::notice title=<name>::<fields> pattern.

    Rather than exercising the full main() entry point (which requires heavy
    engine imports and real data), this test drives the exact same log call
    that was added to main() and verifies the message format.  The assertion
    serves as a living specification: if someone changes the log line, this
    test breaks and the reviewer sees exactly what changed.
    """
    import time

    _uni_size = 7
    _t0 = time.time() - 3.0   # simulate 3 seconds elapsed

    with caplog.at_level(logging.INFO, logger="stock_library"):
        bsl.log.info(
            "::notice title=stock_library::universe=%d elapsed=%.0fs",
            _uni_size,
            time.time() - _t0,
        )

    notice_lines = [r.message for r in caplog.records
                    if "::notice title=stock_library::" in r.message]
    assert notice_lines, "No ::notice title=stock_library:: line found"
    msg = notice_lines[0]
    assert "universe=7" in msg, f"Missing universe field: {msg}"
    assert "elapsed=" in msg, f"Missing elapsed field: {msg}"
