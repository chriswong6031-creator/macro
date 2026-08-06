"""W2-A (Quant Lab masterplan §7): the EDGAR fundamentals universe must reach the
full tracked price universe — S&P 1500 close caches PLUS the Russell 2000 — so the
PIT panel can label the candidates the Signal Episode Atlas actually grades
(1,457 of 2,932 candidate names had no fundamentals rows at all; PR #4677 diagnosis).

The widening reads each group's committed constituents.parquet alongside its
closes cache because russell_breadth's `_closes_cache.parquet` is a gitignored CI
artifact — absent on every fresh checkout — while its constituents table is
committed with never-shrink semantics. The frames-API request count scales with
years×concepts, never tickers, so the wider filter adds no fetch cost.

These tests verify:
  1. Constituents-sourced tickers (russell included) enter the universe even when
     the group has NO closes cache.
  2. Closes-cache columns still enter (back-compat with the original source).
  3. Dropped members from the membership ledger are still retained.
  4. Placeholder/NaN constituents indices are filtered out.
  5. _universe_names picks up russell constituents (feeds the CIK name-match
     fallback for small caps).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar as edgar  # noqa: E402
from lib import config as lib_config  # noqa: E402


def _seed(tmp_path: Path, group: str, closes: list[str] | None = None,
          constituents: dict[str, str] | None = None) -> None:
    d = tmp_path / group
    d.mkdir(parents=True, exist_ok=True)
    if closes is not None:
        pd.DataFrame({t: [1.0] for t in closes},
                     index=[pd.Timestamp("2026-01-02")]).to_parquet(d / "_closes_cache.parquet")
    if constituents is not None:
        meta = pd.DataFrame({"name": list(constituents.values()),
                             "sector": ["X"] * len(constituents)},
                            index=pd.Index(list(constituents.keys()), name="symbol"))
        meta.to_parquet(d / "constituents.parquet")


def test_universe_includes_russell_constituents_without_closes_cache(tmp_path, monkeypatch):
    # russell_breadth ships constituents ONLY (closes cache is a gitignored CI
    # artifact) — its names must still enter the fundamentals universe.
    monkeypatch.setattr(lib_config, "data_dir", lambda: tmp_path)
    _seed(tmp_path, "breadth", closes=["AAPL", "MSFT"], constituents={"AAPL": "Apple Inc"})
    _seed(tmp_path, "russell_breadth", constituents={"HUT": "Hut 8 Corp", "MOG-A": "Moog Inc"})
    uni = edgar._universe_tickers()
    assert {"AAPL", "MSFT", "HUT", "MOG-A"} <= set(uni)


def test_universe_keeps_closes_cache_columns(tmp_path, monkeypatch):
    # A group with a closes cache but no constituents table (or a cache carrying
    # names the constituents scrape has since lost) must not shrink.
    monkeypatch.setattr(lib_config, "data_dir", lambda: tmp_path)
    _seed(tmp_path, "smallcap_breadth", closes=["SGC", "PLAB"])
    uni = edgar._universe_tickers()
    assert {"SGC", "PLAB"} <= set(uni)


def test_universe_retains_dropped_members(tmp_path, monkeypatch):
    # The survivorship half is untouched: ledger-dropped names stay in the universe.
    import engine.universe_history as uh
    monkeypatch.setattr(lib_config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(uh, "dropped_members", lambda: {"GONE"})
    _seed(tmp_path, "breadth", closes=["AAPL"])
    uni = edgar._universe_tickers()
    assert "GONE" in uni and "AAPL" in uni


def test_universe_filters_placeholder_indices(tmp_path, monkeypatch):
    monkeypatch.setattr(lib_config, "data_dir", lambda: tmp_path)
    _seed(tmp_path, "russell_breadth", constituents={"HUT": "Hut 8 Corp", "nan": "Bad Row"})
    uni = edgar._universe_tickers()
    assert "HUT" in uni
    assert "nan" not in uni and "" not in uni


def test_universe_names_reads_russell_constituents(tmp_path, monkeypatch):
    # The CIK name-match fallback needs small-cap company names too.
    monkeypatch.setattr(lib_config, "data_dir", lambda: tmp_path)
    _seed(tmp_path, "breadth", constituents={"AAPL": "Apple Inc"})
    _seed(tmp_path, "russell_breadth", constituents={"BTSG": "BrightSpring Health Services Inc"})
    names = edgar._universe_names()
    assert names.get("BTSG") == "BrightSpring Health Services Inc"
    assert names.get("AAPL") == "Apple Inc"
