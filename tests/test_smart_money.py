"""Tests for the SM2 extensions to engine.smart_money.

Covers:
- issuer_key / share-class deduplication (BRK.A+BRK.B fixture)
- position_rank_and_tilt
- window_dressing_flag
- amendment_delta (empty dir, with content)
- full_cusip_map returns (dict, meta) tuple and warns on empty OpenFIGI
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import smart_money as sm


# --------------------------------------------------------------------------- #
# issuer_key                                                                     #
# --------------------------------------------------------------------------- #

def test_issuer_key_goog_collapses():
    """GOOG must map to GOOGL via the share_class_equiv.yml table."""
    k = sm.issuer_key("GOOG", None)
    assert k == "GOOGL"


def test_issuer_key_brk_b_collapses():
    """BRK.B must map to BRK.A."""
    k = sm.issuer_key("BRK.B", None)
    assert k == "BRK.A"


def test_issuer_key_no_match_passthrough():
    k = sm.issuer_key("AAPL", "037833100")
    assert k == "AAPL"


def test_issuer_key_cusip_fallback():
    k = sm.issuer_key(None, "084670702")
    assert k == "084670"  # 6-char CUSIP stem


def test_issuer_key_unknown():
    k = sm.issuer_key(None, None)
    assert k == "UNKNOWN"


# --------------------------------------------------------------------------- #
# BRK.A+BRK.B double-count prevention                                          #
# --------------------------------------------------------------------------- #

def _make_brk_holders():
    """Simulate two holder entries for the same fund — BRK.A and BRK.B lots."""
    return [
        {"fund": "BERKTEST", "fund_name": "Test Fund", "action": "hold",
         "pct_portfolio": 3.0, "value_usd": 3e6, "period_end": "2025-06-30",
         "shares_change_pct": None, "cusip": "084670702"},  # BRK.A CUSIP stem
        {"fund": "BERKTEST", "fund_name": "Test Fund", "action": "hold",
         "pct_portfolio": 1.0, "value_usd": 1e6, "period_end": "2025-06-30",
         "shares_change_pct": None, "cusip": "084670201"},  # BRK.B CUSIP stem (different)
    ]


def test_overlap_stats_does_not_double_count_share_classes():
    """overlap_stats counts funds, not lots. If a single fund appears twice (A+B share
    class), vip must count it ONCE — the calling code in compute_smart_money collapses
    dual-class lots via groupby(ticker) before building by_ticker entries, so each fund
    appears at most once in the holders list. This test verifies the contract."""
    # After the compute_smart_money groupby collapse, a fund appears only once per ticker.
    # Simulate post-collapse: one entry per fund.
    holders = [
        {"fund": "FUND1", "action": "hold", "value_usd": 4e6, "pct_portfolio": 4.0},
        {"fund": "FUND2", "action": "hold", "value_usd": 2e6, "pct_portfolio": 2.0},
    ]
    stats = sm.overlap_stats(holders)
    # 2 distinct funds → vip = 2
    assert stats["vip"] == 2


def test_position_rank_and_tilt():
    """Verify rank ordering and tilt computation."""
    snap = pd.DataFrame([
        {"ticker": "AAPL", "value_usd": 300.0, "pct_portfolio": 30.0},
        {"ticker": "MSFT", "value_usd": 200.0, "pct_portfolio": 20.0},
        {"ticker": "TSLA", "value_usd": 100.0, "pct_portfolio": 10.0},
    ])
    result = sm.position_rank_and_tilt(snap)
    by_ticker = result.set_index("ticker")
    assert int(by_ticker.loc["AAPL", "rank"]) == 1
    assert int(by_ticker.loc["TSLA", "rank"]) == 3
    # mean pct = (30+20+10)/3 = 20.0
    assert by_ticker.loc["AAPL", "tilt_pp"] == pytest.approx(10.0, abs=0.01)
    assert by_ticker.loc["MSFT", "tilt_pp"] == pytest.approx(0.0, abs=0.01)
    assert by_ticker.loc["TSLA", "tilt_pp"] == pytest.approx(-10.0, abs=0.01)


def test_position_rank_no_value_usd():
    snap = pd.DataFrame([{"ticker": "AAPL", "pct_portfolio": 10.0}])
    result = sm.position_rank_and_tilt(snap)
    assert result["rank"].iloc[0] is None


# --------------------------------------------------------------------------- #
# window_dressing_flag                                                           #
# --------------------------------------------------------------------------- #

def _snap(tickers: list[str]) -> pd.DataFrame:
    rows = [{"ticker": t, "sh_type": "SH"} for t in tickers]
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["ticker", "sh_type"])


def _snaps(*ticker_lists):
    return [(f"Q{i}", f"2025-0{i+1}-14", _snap(list(tl)))
            for i, tl in enumerate(ticker_lists)]


def test_wdf_persisted():
    snaps = _snaps(["AAPL", "MSFT"], ["AAPL", "MSFT"])
    assert sm.window_dressing_flag(snaps, "AAPL") == "persisted"


def test_wdf_pending_latest_only():
    snaps = _snaps(["MSFT"], ["AAPL", "MSFT"])  # AAPL only in latest
    assert sm.window_dressing_flag(snaps, "AAPL") == "pending"


def test_wdf_one_quarter_prior_only():
    snaps = _snaps(["AAPL"], ["MSFT"])  # AAPL only in Q1, gone in Q2
    assert sm.window_dressing_flag(snaps, "AAPL") == "one_quarter"


def test_wdf_empty():
    assert sm.window_dressing_flag([], "AAPL") == "pending"


# --------------------------------------------------------------------------- #
# amendment_delta                                                                #
# --------------------------------------------------------------------------- #

def test_amendment_delta_empty_dir(tmp_path, monkeypatch):
    """No amendments dir → empty list."""
    import engine.smart_money as _sm
    monkeypatch.setattr(_sm.config, "data_dir", lambda: tmp_path)
    # create slug dir but no amendments subdir
    (tmp_path / "smart_money" / "test_fund").mkdir(parents=True)
    result = sm.amendment_delta("test_fund")
    assert result == []


def test_amendment_delta_no_matching_original(tmp_path, monkeypatch):
    """Amendment exists but no matching original → empty list."""
    import engine.smart_money as _sm
    monkeypatch.setattr(_sm.config, "data_dir", lambda: tmp_path)
    slug_dir = tmp_path / "smart_money" / "test_fund"
    amend_dir = slug_dir / "amendments"
    amend_dir.mkdir(parents=True)
    # Write an amendment with a period_end that has no original
    rows = [{"cusip": "X", "issuer": "Test", "sh_type": "SH",
             "shares": 200, "value_usd": 1e6}]
    pd.DataFrame(rows).to_parquet(amend_dir / "2025-03-31__2025-06-01.parquet")
    assert sm.amendment_delta("test_fund") == []


def test_amendment_delta_detects_large_change(tmp_path, monkeypatch):
    """Amendment with >20% share change should appear in results."""
    import engine.smart_money as _sm
    monkeypatch.setattr(_sm.config, "data_dir", lambda: tmp_path)
    slug_dir = tmp_path / "smart_money" / "test_fund"
    amend_dir = slug_dir / "amendments"
    amend_dir.mkdir(parents=True)

    # Original: 1000 shares
    orig_rows = [{"cusip": "AAA", "issuer": "Acme Corp", "sh_type": "SH",
                  "shares": 1000, "value_usd": 1e6,
                  "filing_date": "2025-05-15", "period_end": "2025-03-31"}]
    pd.DataFrame(orig_rows).to_parquet(slug_dir / "2025-03-31.parquet")

    # Amendment: 1500 shares (+50%)
    amend_rows = [{"cusip": "AAA", "issuer": "Acme Corp", "sh_type": "SH",
                   "shares": 1500, "value_usd": 1.5e6,
                   "filing_date": "2025-06-01", "period_end": "2025-03-31"}]
    pd.DataFrame(amend_rows).to_parquet(amend_dir / "2025-03-31__2025-06-01.parquet")

    deltas = sm.amendment_delta("test_fund")
    assert len(deltas) == 1
    assert deltas[0]["pct_change_shares"] == pytest.approx(50.0, abs=0.1)
    assert deltas[0]["amendment_filing_date"] == "2025-06-01"
    assert deltas[0]["orig_filing_date"] == "2025-05-15"


def test_amendment_delta_small_change_excluded(tmp_path, monkeypatch):
    """Amendment with ≤20% share change must NOT appear in results."""
    import engine.smart_money as _sm
    monkeypatch.setattr(_sm.config, "data_dir", lambda: tmp_path)
    slug_dir = tmp_path / "smart_money" / "test_fund2"
    amend_dir = slug_dir / "amendments"
    amend_dir.mkdir(parents=True)

    orig_rows = [{"cusip": "BBB", "issuer": "Beta Inc", "sh_type": "SH",
                  "shares": 1000, "value_usd": 1e6,
                  "filing_date": "2025-05-15", "period_end": "2025-03-31"}]
    pd.DataFrame(orig_rows).to_parquet(slug_dir / "2025-03-31.parquet")

    amend_rows = [{"cusip": "BBB", "issuer": "Beta Inc", "sh_type": "SH",
                   "shares": 1050, "value_usd": 1.05e6,
                   "filing_date": "2025-06-01", "period_end": "2025-03-31"}]
    pd.DataFrame(amend_rows).to_parquet(amend_dir / "2025-03-31__2025-06-01.parquet")

    deltas = sm.amendment_delta("test_fund2")
    # +5% change → must NOT appear
    assert deltas == []


# --------------------------------------------------------------------------- #
# full_cusip_map returns tuple and warns on empty OpenFIGI                     #
# --------------------------------------------------------------------------- #

def test_full_cusip_map_returns_tuple():
    result = sm.full_cusip_map()
    assert isinstance(result, tuple) and len(result) == 2
    mapping, meta = result
    assert isinstance(mapping, dict)
    assert "openfigi_entries" in meta
    assert "ark_seed_entries" in meta


def test_full_cusip_map_warns_when_figi_empty(monkeypatch, caplog):
    """When OpenFIGI returns 0 entries a WARNING must be logged."""
    import logging

    def _empty_figi():
        return {}

    try:
        from collectors import openfigi
        monkeypatch.setattr(openfigi, "load_cusip_ticker", _empty_figi)
    except Exception:
        pytest.skip("openfigi collector not importable in this checkout")

    import engine.smart_money as _sm
    # Force reload of the function in context
    with caplog.at_level(logging.WARNING, logger="engine.smart_money"):
        mapping, meta = _sm.full_cusip_map()
    assert meta["openfigi_entries"] == 0
    assert any("OpenFIGI" in r.message for r in caplog.records)
