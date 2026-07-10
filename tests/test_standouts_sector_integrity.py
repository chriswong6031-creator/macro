"""Sector-label integrity for the us_standouts producer (PR #2113 issue 4).

data/sector_holdings/ holds per-fund top-N snapshots (XLB..XLY) PLUS two
cross-fund log files (history.parquet — the PIT archiver, holdings_runs.parquet).
build_stock_library.universe() built its deep-history name/sector map by globbing
*.parquet and using each file's stem as the sector-label key — history.parquet has
a `ticker` column, so it survived the old holdings_runs guard and stamped every
ticker it logged with sector="history" (QCOM shipped on the buy lane that way).

Covers the two fixes:
  1. universe() skips non-fund parquets (stem not in SECTOR_NAMES) and bridges
     the SPDR display vocabulary to GICS (Technology -> Information Technology),
     so the artifact carries ONE sector vocabulary.
  2. _drop_spurious_sector_rows() — the write-side backstop: any lane row whose
     sector is non-empty and not one of the 11 GICS names is dropped before the
     artifact is written. Empty sector = unknown metadata, retained.
"""
import numpy as np
import pandas as pd
import pytest

import scripts.build_stock_library as bsl
from engine.playbook import SECTOR_NAMES


# ---------------------------------------------------------------------------
# 1. write-side backstop
# ---------------------------------------------------------------------------

def _row(ticker, sector):
    return {"ticker": ticker, "sector": sector, "alpha": 0.1}


class TestDropSpuriousSectorRows:
    def test_history_row_dropped_from_buy(self):
        wide = {"buy": [_row("QCOM", "history"), _row("AAPL", "Information Technology")],
                "watch": [], "laggards": []}
        dropped = bsl._drop_spurious_sector_rows(wide)
        assert dropped == {"buy": [("QCOM", "history")]}
        assert [r["ticker"] for r in wide["buy"]] == ["AAPL"]

    def test_all_lanes_are_guarded(self):
        wide = {"buy": [_row("A", "history")],
                "watch": [_row("B", "holdings_runs")],
                "laggards": [_row("C", "not-a-sector")]}
        dropped = bsl._drop_spurious_sector_rows(wide)
        assert set(dropped) == {"buy", "watch", "laggards"}
        assert wide["buy"] == wide["watch"] == wide["laggards"] == []

    def test_gics_and_empty_sectors_are_kept(self):
        rows = [_row(f"T{i}", s) for i, s in enumerate(sorted(bsl.GICS_SECTORS))]
        rows += [_row("NOSEC", ""), _row("NONE", None)]
        wide = {"buy": list(rows), "watch": [], "laggards": []}
        dropped = bsl._drop_spurious_sector_rows(wide)
        assert dropped == {}
        assert len(wide["buy"]) == len(rows)

    def test_spdr_display_names_are_not_valid_row_sectors(self):
        # universe() bridges SPDR vocab to GICS at the source; a raw SPDR name
        # reaching the board means the bridge was bypassed — treat as corrupt.
        wide = {"buy": [_row("QCOM", "Technology")], "watch": [], "laggards": []}
        dropped = bsl._drop_spurious_sector_rows(wide)
        assert dropped == {"buy": [("QCOM", "Technology")]}


def test_spdr_bridge_covers_every_sector_fund_label():
    """Every XL* fund label maps into the 11 GICS names via the bridge."""
    bridged = {bsl._SPDR_TO_GICS.get(v, v)
               for k, v in SECTOR_NAMES.items() if k.startswith("XL")}
    assert bridged <= bsl.GICS_SECTORS


# ---------------------------------------------------------------------------
# 2. universe() source hardening
# ---------------------------------------------------------------------------

def _close_frame(n=300):
    idx = pd.bdate_range("2025-01-01", periods=n)
    close = pd.Series(100.0 * np.exp(np.cumsum(np.full(n, 0.0002))), index=idx)
    return pd.DataFrame({"close": close, "high": close * 1.01})


@pytest.fixture
def fake_data_dir(tmp_path, monkeypatch):
    hd = tmp_path / "sector_holdings"
    hd.mkdir()
    pd.DataFrame({"ticker": ["QCOM"], "name": ["QUALCOMM INC"],
                  "weight_pct": [1.32], "rank": [19]}).to_parquet(hd / "XLK.parquet")
    # the PIT archiver: has a ticker column, must still be skipped
    pd.DataFrame({"as_of": [pd.Timestamp("2026-07-08")], "etf": ["XLK"],
                  "ticker": ["QCOM"], "name": ["QUALCOMM CLOBBERED"],
                  "weight_pct": [1.32], "rank": [19]}).to_parquet(hd / "history.parquet")
    # the runs summary: no ticker column
    pd.DataFrame({"run": ["2026-07-08"], "ok": [11]}).to_parquet(hd / "holdings_runs.parquet")
    sd = tmp_path / "stocks"
    sd.mkdir()
    _close_frame().to_parquet(sd / "QCOM.parquet")
    monkeypatch.setattr(bsl.config, "data_dir", lambda: tmp_path)
    return tmp_path


def test_universe_skips_cross_fund_logs_and_emits_gics(fake_data_dir):
    uni = bsl.universe()
    by_ticker = {t: (name, sector) for t, _, _, name, sector in uni}
    assert "QCOM" in by_ticker
    name, sector = by_ticker["QCOM"]
    # history.parquet must not clobber the fund label or the name
    assert sector == "Information Technology"
    assert name == "Qualcomm Inc"
    # no row anywhere may carry a file-stem sector
    assert not [t for t, (_, s) in by_ticker.items() if s in ("history", "holdings_runs")]
