"""Tests for the new-sponsor ETF holdings path + the cross-fund consensus engine.

Two layers under test:
  * collectors.etf_holdings.EtfHoldingsAdapter._normalize — the shared numeric
    coercion + non-equity drop that every sponsor adapter funnels through. We feed
    it small in-memory frames shaped like each new sponsor's post-column-rename
    output ('$'/','/'%' laden strings, a cash/FX line, a foreign-listed equity, a
    blank-shares row) and assert the clean [ticker,name,weight_pct,shares,
    market_value,as_of] contract.
  * engine.etf_consensus — consensus_favored (pure, tested with a synthetic
    all_etf_signals() rows list) and weight_trajectory / fund_coverage (store-backed,
    tested against tempfile parquet snapshots with config monkeypatched by
    save-and-restore — NO pytest fixtures, so the file stays runnable as a script).

Everything is in-memory or tmpfile; nothing hits the network. Matches the
save-and-restore / __main__-harness style of tests/test_holdings_signals.py."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.etf_holdings import EtfHoldingsAdapter  # noqa: E402
from engine import etf_consensus as ec  # noqa: E402
from lib import config  # noqa: E402


# =============================================================================
# A) _normalize — new-sponsor raw shapes
# =============================================================================

def test_normalize_vaneck_ssga_shape_parses_currency_symbols() -> None:
    # VanEck / SSGA-like post-rename frame: weight carries '%', shares carry ','
    # and market_value carries '$'+','+'.'. _normalize's num() strips [,$%()].
    df = pd.DataFrame({
        "ticker": ["NVDA", "AAPL"],
        "name": ["NVIDIA CORP", "APPLE INC"],
        "%_of_net_assets": ["10.53%", "8.20%"],
        "shares": ["25,652,285", "12,000,000"],
        "market_value": ["$2,432,093,140.85", "$1,000,000,000.00"],
    })
    out = EtfHoldingsAdapter._normalize(df, "TEST", "2026-07-10",
                                        wcol="%_of_net_assets", scol="shares",
                                        mcol="market_value")
    assert list(out.columns) == ["ticker", "name", "weight_pct", "shares",
                                 "market_value", "as_of"]
    nv = out[out.ticker == "NVDA"].iloc[0]
    assert nv["weight_pct"] == 10.53                       # '%' stripped
    assert nv["shares"] == 25_652_285                      # ',' stripped
    assert abs(nv["market_value"] - 2_432_093_140.85) < 1e-2   # '$' + ',' stripped
    assert (out["as_of"] == "2026-07-10").all()
    assert list(out["ticker"]) == ["NVDA", "AAPL"]


def test_normalize_drops_cash_and_fx_rows() -> None:
    # A CASH line, an FX/currency ticker, and an "OTHER PAYABLE & RECEIVABLES"
    # line must all be dropped by is_non_equity_holding; the real equity survives.
    df = pd.DataFrame({
        "ticker": ["MSFT", "USD", "-", "XYZ"],
        "name": ["MICROSOFT CORP", "US Dollar", "Cash&Other",
                 "OTHER PAYABLE & RECEIVABLES"],
        "%_of_net_assets": ["7.10%", "1.50%", "0.90%", "0.30%"],
        "shares": ["5,000,000", "9,999,999", "1,000", "2,000"],
        "market_value": ["$500,000,000", "$9,999,999", "$1,000", "$2,000"],
    })
    out = EtfHoldingsAdapter._normalize(df, "TEST", "2026-07-10",
                                        wcol="%_of_net_assets", scol="shares",
                                        mcol="market_value")
    assert list(out["ticker"]) == ["MSFT"]                 # only the real equity
    assert out.iloc[0]["shares"] == 5_000_000


def test_normalize_keeps_foreign_listed_equities() -> None:
    # Real foreign-listed equities ('1211 HK', 'PDN AU') have genuine share counts
    # and must NOT be swept out as non-equity.
    df = pd.DataFrame({
        "ticker": ["1211 HK", "PDN AU", "AAPL"],
        "name": ["BYD CO LTD-H", "PALADIN ENERGY LTD", "APPLE INC"],
        "%_of_net_assets": ["3.10%", "2.00%", "8.00%"],
        "shares": ["4,000,000", "6,500,000", "10,000,000"],
        "market_value": ["$300,000,000", "$120,000,000", "$1,700,000,000"],
    })
    out = EtfHoldingsAdapter._normalize(df, "TEST", "2026-07-10",
                                        wcol="%_of_net_assets", scol="shares",
                                        mcol="market_value")
    assert set(out["ticker"]) == {"1211 HK", "PDN AU", "AAPL"}   # all kept
    assert out[out.ticker == "1211 HK"].iloc[0]["shares"] == 4_000_000


def test_normalize_drops_blank_shares_row() -> None:
    # A row whose shares cell is blank / non-numeric coerces to NaN and is dropped
    # by the .dropna(subset=["shares"]) guard.
    df = pd.DataFrame({
        "ticker": ["AMD", "GHOST"],
        "name": ["ADVANCED MICRO DEVICES", "No Share Co"],
        "%_of_net_assets": ["4.00%", "1.00%"],
        "shares": ["3,000,000", ""],
        "market_value": ["$400,000,000", "$0"],
    })
    out = EtfHoldingsAdapter._normalize(df, "TEST", "2026-07-10",
                                        wcol="%_of_net_assets", scol="shares",
                                        mcol="market_value")
    assert list(out["ticker"]) == ["AMD"]                  # blank-shares row dropped
    assert out.iloc[0]["shares"] == 3_000_000


def test_normalize_raises_when_all_rows_dropped() -> None:
    # Only cash/FX rows => nothing survives => ValueError so the breaker can see it.
    df = pd.DataFrame({
        "ticker": ["USD", "EUR"],
        "name": ["US Dollar", "Euro Cash"],
        "%_of_net_assets": ["50%", "50%"],
        "shares": ["100", "200"],
        "market_value": ["$100", "$200"],
    })
    raised = False
    try:
        EtfHoldingsAdapter._normalize(df, "EMPTY", "2026-07-10",
                                      wcol="%_of_net_assets", scol="shares",
                                      mcol="market_value")
    except ValueError:
        raised = True
    assert raised, "expected ValueError when no equity rows survive normalization"


# =============================================================================
# B) consensus_favored — cross-fund grouping math
# =============================================================================

def _row(etf, ticker, conviction_pp, direction, *, name=None, sector="Tech",
         is_new=False, is_exit=False, is_active=True, etf_name=None,
         category="Active", weight_pct=None, active_chg_pct=None,
         ladder=None, confirmed=False) -> dict:
    """Build one all_etf_signals()-shaped row (the consensus input contract)."""
    return {
        "etf": etf, "etf_name": etf_name or etf, "category": category,
        "is_active": is_active, "ticker": ticker, "name": name or ticker,
        "sector": sector, "weight_pct": weight_pct, "active_chg_pct": active_chg_pct,
        "conviction_pp": conviction_pp, "is_new": is_new, "is_exit": is_exit,
        "direction": direction, "ladder": ladder, "confirmed": confirmed,
    }


def _stub_cfg():
    """Neutralize etf_consensus._cfg()/config.load() so consensus_favored uses its
    own passed args and never touches the real config. Save-and-restore."""
    orig = config.load
    config.load = lambda: {"etf_holdings": {}}
    return orig


def _synthetic_rows() -> list[dict]:
    return [
        # BUG — accumulated by 3 funds (broad, high-conviction; 1 fund is NEW).
        _row("FUNDA", "BUG", 5.3, "accumulating", name="Big Bug Co"),
        _row("FUNDB", "BUG", 2.1, "accumulating"),
        _row("FUNDC", "BUG", 0.9, "accumulating", is_new=True),
        # LONE — trimmed by exactly 1 fund (single-fund name).
        _row("FUNDA", "LONE", -3.0, "trimming"),
        # SPLIT — contested: one fund adds, one fund trims.
        _row("FUNDA", "SPLIT", 4.0, "accumulating"),
        _row("FUNDB", "SPLIT", -1.5, "trimming"),
        # GONE — a full exit from 1 fund.
        _row("FUNDB", "GONE", -2.5, "trimming", is_exit=True),
        # a conviction_pp=None row must be skipped entirely (no ticker group formed).
        _row("FUNDA", "SKIPME", None, "accumulating"),
    ]


def test_consensus_groups_and_counts() -> None:
    orig = _stub_cfg()
    try:
        out = ec.consensus_favored(rows=_synthetic_rows(), min_funds=1)
    finally:
        config.load = orig
    by = {g["ticker"]: g for g in out}

    assert "SKIPME" not in by                       # conviction_pp=None skipped
    # BUG: 3 accumulating funds, 1 of them new; net = 5.3+2.1+0.9 = 8.3
    bug = by["BUG"]
    assert bug["n_accum"] == 3 and bug["n_trim"] == 0
    assert bug["n_new"] == 1 and bug["n_exit"] == 0
    assert abs(bug["net_conviction_pp"] - 8.3) < 1e-9
    assert abs(bug["gross_conviction_pp"] - 8.3) < 1e-9
    assert bug["contested"] is False and bug["direction"] == "accumulating"

    # LONE: single trimming fund
    lone = by["LONE"]
    assert lone["n_accum"] == 0 and lone["n_trim"] == 1
    assert abs(lone["net_conviction_pp"] - (-3.0)) < 1e-9
    assert lone["direction"] == "distributing"

    # SPLIT: contested (one add, one trim); net = 4.0-1.5 = 2.5, gross = 5.5
    split = by["SPLIT"]
    assert split["n_accum"] == 1 and split["n_trim"] == 1
    assert split["contested"] is True
    assert abs(split["net_conviction_pp"] - 2.5) < 1e-9
    assert abs(split["gross_conviction_pp"] - 5.5) < 1e-9

    # GONE: full exit counted
    gone = by["GONE"]
    assert gone["n_exit"] == 1 and gone["n_trim"] == 1


def test_consensus_breadth_first_ranking() -> None:
    orig = _stub_cfg()
    try:
        out = ec.consensus_favored(rows=_synthetic_rows(), min_funds=1)
    finally:
        config.load = orig
    order = [g["ticker"] for g in out]
    # BUG (3 accumulating funds) must rank ABOVE SPLIT/LONE (single-add breadth).
    assert order[0] == "BUG"
    assert order.index("BUG") < order.index("SPLIT")
    assert order.index("BUG") < order.index("LONE")


def test_consensus_funds_sorted_by_abs_conviction() -> None:
    orig = _stub_cfg()
    try:
        out = ec.consensus_favored(rows=_synthetic_rows(), min_funds=1)
    finally:
        config.load = orig
    bug = next(g for g in out if g["ticker"] == "BUG")
    convs = [f["conviction_pp"] for f in bug["funds"]]
    # sorted by |conviction_pp| descending: 5.3, 2.1, 0.9
    assert convs == sorted(convs, key=lambda c: -abs(c))
    assert convs[0] == 5.3


def test_consensus_min_funds_filters_single_fund_names() -> None:
    orig = _stub_cfg()
    try:
        out = ec.consensus_favored(rows=_synthetic_rows(), min_funds=2)
    finally:
        config.load = orig
    tickers = {g["ticker"] for g in out}
    # BUG (3 funds) and SPLIT (2 funds) survive; LONE/GONE (1 fund each) filtered.
    assert "BUG" in tickers and "SPLIT" in tickers
    assert "LONE" not in tickers and "GONE" not in tickers


def test_consensus_empty_and_none_conviction() -> None:
    orig = _stub_cfg()
    try:
        assert ec.consensus_favored(rows=[], min_funds=1) == []
        # a lone row whose conviction_pp is None yields no groups at all
        only_none = [_row("FUNDA", "NOPE", None, "accumulating")]
        assert ec.consensus_favored(rows=only_none, min_funds=1) == []
    finally:
        config.load = orig


# =============================================================================
# C) weight_trajectory + fund_coverage — store-backed (tempfile parquet)
# =============================================================================

def _write_snapshot(fund_dir: Path, asof: str, rows: list[dict]) -> None:
    fund_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df["as_of"] = asof
    df.to_parquet(fund_dir / f"{asof}.parquet")


def _install_fake_store(tmp: Path):
    """Point etf_consensus's config at a tmp tree with a synthetic storage config.
    _fund_snapshot_dir / fund_coverage scan two roots:
        config.data_dir()/etf_holdings/<FUND>
        config.ROOT/<storage.holdings_dir>/<FUND>
    We stub data_dir, ROOT and load (save-and-restore). Returns the originals."""
    orig_load = config.load
    orig_data_dir = config.data_dir
    orig_root = config.ROOT

    cfg = {
        "storage": {"holdings_dir": "data/holdings"},
        "etf_holdings": {
            "universe": {"TESTF": {"name": "Test Fund", "sponsor": "ssga",
                                   "category": "Sector"}}
        },
        "holdings": {"watchlist": {}},
    }
    config.load = lambda: cfg
    config.data_dir = lambda: tmp / "data"
    config.ROOT = tmp
    return orig_load, orig_data_dir, orig_root


def _restore_store(orig) -> None:
    config.load, config.data_dir, config.ROOT = orig


def test_weight_trajectory_oldest_to_newest() -> None:
    tmp = Path(tempfile.mkdtemp())
    fund_dir = tmp / "data" / "etf_holdings" / "TESTF"
    _write_snapshot(fund_dir, "2026-07-08",
                    [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 9.0,
                      "shares": 100, "market_value": 900},
                     {"ticker": "AAPL", "name": "Apple", "weight_pct": 5.0,
                      "shares": 50, "market_value": 250}])
    _write_snapshot(fund_dir, "2026-07-09",
                    [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 10.5,
                      "shares": 120, "market_value": 1260},
                     {"ticker": "AAPL", "name": "Apple", "weight_pct": 4.5,
                      "shares": 45, "market_value": 202}])
    _write_snapshot(fund_dir, "2026-07-10",
                    [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 11.2,
                      "shares": 130, "market_value": 1456}])
    orig = _install_fake_store(tmp)
    try:
        traj = ec.weight_trajectory("TESTF", "NVDA", k=12)
        # oldest -> newest, one point per snapshot that holds the ticker
        assert [p["as_of"] for p in traj] == ["2026-07-08", "2026-07-09", "2026-07-10"]
        assert [p["weight_pct"] for p in traj] == [9.0, 10.5, 11.2]

        # AAPL absent from the newest snapshot -> only the two snaps that hold it
        aapl = ec.weight_trajectory("TESTF", "AAPL", k=12)
        assert [p["weight_pct"] for p in aapl] == [5.0, 4.5]

        # absent ticker / absent fund -> []
        assert ec.weight_trajectory("TESTF", "ZZZZ", k=12) == []
        assert ec.weight_trajectory("NOSUCH", "NVDA", k=12) == []
    finally:
        _restore_store(orig)


def test_attach_trajectories_populates_weight_series() -> None:
    tmp = Path(tempfile.mkdtemp())
    fund_dir = tmp / "data" / "etf_holdings" / "TESTF"
    _write_snapshot(fund_dir, "2026-07-08",
                    [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 9.0,
                      "shares": 100, "market_value": 900}])
    _write_snapshot(fund_dir, "2026-07-09",
                    [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 10.5,
                      "shares": 120, "market_value": 1260}])
    orig = _install_fake_store(tmp)
    try:
        rows = [{"etf": "TESTF", "ticker": "NVDA"},
                {"etf": "TESTF", "ticker": "ZZZZ"}]
        ec.attach_trajectories(rows, k=12, cap=None)
        assert rows[0]["weight_series"] == [9.0, 10.5]     # oldest->newest floats
        assert rows[1]["weight_series"] == []              # absent ticker
        # cap bounds the parquet reads: rows past the cap get an empty series
        rows2 = [{"etf": "TESTF", "ticker": "NVDA"},
                 {"etf": "TESTF", "ticker": "NVDA"}]
        ec.attach_trajectories(rows2, k=12, cap=1)
        assert rows2[0]["weight_series"] == [9.0, 10.5]
        assert rows2[1]["weight_series"] == []             # beyond cap
    finally:
        _restore_store(orig)


def test_fund_coverage_reports_depth_and_freshness() -> None:
    tmp = Path(tempfile.mkdtemp())
    fund_dir = tmp / "data" / "etf_holdings" / "TESTF"
    _write_snapshot(fund_dir, "2026-07-08",
                    [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 9.0,
                      "shares": 100, "market_value": 900}])
    _write_snapshot(fund_dir, "2026-07-10",
                    [{"ticker": "NVDA", "name": "NVIDIA", "weight_pct": 11.2,
                      "shares": 130, "market_value": 1456}])
    orig = _install_fake_store(tmp)
    try:
        cov = ec.fund_coverage()
        by = {c["fund"]: c for c in cov}
        assert "TESTF" in by
        f = by["TESTF"]
        assert f["n_snapshots"] == 2
        assert f["latest_asof"] == "2026-07-10"
        assert f["fund_name"] == "Test Fund"
        assert f["is_active"] is False
        # newest snapshot in the fleet is TESTF's own 2026-07-10 -> 0 days stale,
        # and stale_days must be a real integer, not None.
        assert isinstance(f["stale_days"], int)
        assert f["stale_days"] == 0
    finally:
        _restore_store(orig)


if __name__ == "__main__":
    tests = [
        test_normalize_vaneck_ssga_shape_parses_currency_symbols,
        test_normalize_drops_cash_and_fx_rows,
        test_normalize_keeps_foreign_listed_equities,
        test_normalize_drops_blank_shares_row,
        test_normalize_raises_when_all_rows_dropped,
        test_consensus_groups_and_counts,
        test_consensus_breadth_first_ranking,
        test_consensus_funds_sorted_by_abs_conviction,
        test_consensus_min_funds_filters_single_fund_names,
        test_consensus_empty_and_none_conviction,
        test_weight_trajectory_oldest_to_newest,
        test_attach_trajectories_populates_weight_series,
        test_fund_coverage_reports_depth_and_freshness,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    if failed:
        print(f"{failed}/{len(tests)} FAILED")
        sys.exit(1)
    print("all etf-new-sponsor tests passed")
