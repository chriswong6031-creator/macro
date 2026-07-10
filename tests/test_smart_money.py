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
    """Simulate two holder entries for the same fund — BRK.A and BRK.B lots.
    NOTE: This fixture is retained for reference but is no longer used directly
    by tests. The M4 de-theater test below uses compute_smart_money directly."""
    return [
        {"fund": "BERKTEST", "fund_name": "Test Fund", "action": "hold",
         "pct_portfolio": 3.0, "value_usd": 3e6, "period_end": "2025-06-30",
         "shares_change_pct": None, "cusip": "084670702"},  # BRK.A CUSIP stem
        {"fund": "BERKTEST", "fund_name": "Test Fund", "action": "hold",
         "pct_portfolio": 1.0, "value_usd": 1e6, "period_end": "2025-06-30",
         "shares_change_pct": None, "cusip": "084670201"},  # BRK.B CUSIP stem (different)
    ]


def test_overlap_stats_does_not_double_count_share_classes(tmp_path, monkeypatch):
    """Funds holding both GOOG and GOOGL must be counted ONCE in n_funds.

    This test pushes genuinely un-collapsed GOOG+GOOGL rows through the real
    compute_smart_money aggregation path. We assert:
    - n_funds counts each fund once (not once per share class)
    - total_value sums both classes
    - both GOOG and GOOGL resolve in by_ticker to the same canonical record
    - most_held has only the canonical row (no duplicate entry)
    """
    import engine.smart_money as _sm

    monkeypatch.setattr(_sm.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_sm.config, "load", lambda: {
        "smart_money": {
            "panel_top_n": 12,
            "funds": {
                "fund_alpha": {"name": "Fund Alpha"},
                "fund_beta": {"name": "Fund Beta"},
            },
        }
    })

    # Fund Alpha holds GOOG (class C) + GOOGL (class A) — two 13F lines per SEC rules
    alpha_dir = tmp_path / "smart_money" / "fund_alpha"
    alpha_dir.mkdir(parents=True)
    # GOOG CUSIP: 02079K107; GOOGL CUSIP: 02079K305 (real, different stems)
    snap_alpha = pd.DataFrame([
        {"cusip": "02079K107", "issuer": "ALPHABET INC CLASS C", "sh_type": "SH",
         "shares": 500.0, "value_usd": 900_000.0,
         "period_end": "2025-12-31", "filing_date": "2026-02-14"},
        {"cusip": "02079K305", "issuer": "ALPHABET INC CLASS A", "sh_type": "SH",
         "shares": 300.0, "value_usd": 600_000.0,
         "period_end": "2025-12-31", "filing_date": "2026-02-14"},
    ])
    snap_alpha.to_parquet(alpha_dir / "2025-12-31.parquet")

    # Fund Beta holds GOOGL only
    beta_dir = tmp_path / "smart_money" / "fund_beta"
    beta_dir.mkdir(parents=True)
    snap_beta = pd.DataFrame([
        {"cusip": "02079K305", "issuer": "ALPHABET INC CLASS A", "sh_type": "SH",
         "shares": 1000.0, "value_usd": 2_000_000.0,
         "period_end": "2025-12-31", "filing_date": "2026-02-20"},
    ])
    snap_beta.to_parquet(beta_dir / "2025-12-31.parquet")

    # Monkeypatch resolution: GOOG -> GOOG, GOOGL -> GOOGL by CUSIP
    monkeypatch.setattr(_sm, "name_ticker_map", lambda *a, **kw: {})
    monkeypatch.setattr(_sm, "full_cusip_map", lambda *a, **kw: (
        {"02079K107": "GOOG", "02079K305": "GOOGL"},
        {"openfigi_entries": 2, "ark_seed_entries": 0},
    ))
    monkeypatch.setattr(_sm, "_accumulation", lambda *a, **kw: {})
    monkeypatch.setattr(_sm, "_safe_manager_quality", lambda *a, **kw: {})

    result = _sm.compute_smart_money({
        "panel_top_n": 12,
        "funds": {
            "fund_alpha": {"name": "Fund Alpha"},
            "fund_beta": {"name": "Fund Beta"},
        },
    })
    assert result is not None, "compute_smart_money returned None"

    # 1. most_held must have only the canonical row (GOOGL), not both GOOG and GOOGL
    most_held_tickers = [r["ticker"] for r in result["most_held"]]
    assert "GOOG" not in most_held_tickers, (
        f"GOOG must NOT appear as a separate most_held row; got {most_held_tickers}")
    assert "GOOGL" in most_held_tickers, "GOOGL canonical row must be in most_held"

    # 2. n_funds for the canonical row: fund_alpha (holds both GOOG+GOOGL) counts ONCE
    # + fund_beta = 2 total, not 3
    canon_row = next(r for r in result["most_held"] if r["ticker"] == "GOOGL")
    assert canon_row["n_funds"] == 2, (
        f"Expected n_funds=2 (fund_alpha once + fund_beta), got {canon_row['n_funds']}")

    # 3. total_value sums both classes: alpha=900k+600k=1.5M + beta=2M = 3.5M
    assert canon_row["total_value"] == pytest.approx(3_500_000.0, rel=0.01), (
        f"Expected total_value≈3.5M, got {canon_row['total_value']}")

    # 4. Both GOOG and GOOGL must resolve in by_ticker to the same canonical record
    by_ticker = result["by_ticker"]
    assert "GOOGL" in by_ticker, "Canonical GOOGL must be in by_ticker"
    assert "GOOG" in by_ticker, "Alias GOOG must be in by_ticker"
    assert by_ticker["GOOG"] is by_ticker["GOOGL"], (
        "GOOG and GOOGL must point to the same canonical by_ticker record")


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


# --------------------------------------------------------------------------- #
# E2.5 fixes: shares + issuer propagation into holder records                  #
# --------------------------------------------------------------------------- #

def _make_snapshot_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal 13F snapshot DataFrame for testing."""
    return pd.DataFrame(rows)


def test_diff_snapshots_preserves_shares():
    """diff_snapshots must retain the 'shares' column in its output (E2.5 fix)."""
    latest = _make_snapshot_df([
        {"cusip": "AAPL01", "issuer": "APPLE INC", "sh_type": "SH",
         "shares": 10000.0, "value_usd": 1_600_000.0},
        {"cusip": "MSFT01", "issuer": "MICROSOFT CORP", "sh_type": "SH",
         "shares": 5000.0, "value_usd": 1_900_000.0},
    ])
    diff = sm.diff_snapshots(None, latest)
    assert "shares" in diff.columns, "diff_snapshots must preserve 'shares' column"
    # Sum per cusip (aggregated by diff_snapshots groupby)
    shares_map = dict(zip(diff["cusip"], diff["shares"]))
    assert shares_map["AAPL01"] == pytest.approx(10000.0)
    assert shares_map["MSFT01"] == pytest.approx(5000.0)


def test_compute_smart_money_holder_has_shares(tmp_path, monkeypatch):
    """Each holder entry in by_ticker must carry a 'shares' field after E2.5 fix.

    Uses a minimal two-snapshot fixture to avoid disk reads.
    """
    import engine.smart_money as _sm

    # Monkeypatch data dir + fund config
    monkeypatch.setattr(_sm.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_sm.config, "load", lambda: {
        "smart_money": {
            "panel_top_n": 12,
            "funds": {"testfund": {"name": "Test Fund"}},
        }
    })

    # Write a minimal snapshot
    snap_dir = tmp_path / "smart_money" / "testfund"
    snap_dir.mkdir(parents=True)
    snap = pd.DataFrame([
        {"cusip": "AAP001", "issuer": "APPLE INC", "sh_type": "SH",
         "shares": 12345.0, "value_usd": 2_000_000.0,
         "fund_slug": "testfund", "period_end": "2025-12-31", "filing_date": "2026-02-14"},
    ])
    snap.to_parquet(snap_dir / "2025-12-31.parquet")

    # Monkeypatch name_ticker_map — keys must be _norm()-normalized form of issuer names
    # _norm("APPLE INC") = "APPLE" (suffixes dropped)
    monkeypatch.setattr(_sm, "name_ticker_map", lambda *a, **kw: {"APPLE": "AAPL"})
    # Monkeypatch full_cusip_map to use CUSIP as the primary resolution path
    monkeypatch.setattr(_sm, "full_cusip_map", lambda *a, **kw: ({"AAP001": "AAPL"}, {"openfigi_entries": 0, "ark_seed_entries": 0}))
    # Monkeypatch accumulation trend + quality (not relevant here)
    monkeypatch.setattr(_sm, "_accumulation", lambda *a, **kw: {})
    monkeypatch.setattr(_sm, "_safe_manager_quality", lambda *a, **kw: {})

    result = _sm.compute_smart_money({
        "panel_top_n": 12,
        "funds": {"testfund": {"name": "Test Fund"}},
    })
    assert result is not None
    by_ticker = result.get("by_ticker", {})
    assert "AAPL" in by_ticker, "AAPL should be resolved from fixture snapshot"
    holders = by_ticker["AAPL"]["holders"]
    assert len(holders) >= 1
    h = holders[0]
    assert "shares" in h, "holder entry must carry 'shares' field (E2.5 fix)"
    assert h["shares"] == pytest.approx(12345.0)
    assert "issuer" in h, "holder entry must carry 'issuer' field (E2.5 fix)"
    assert "APPLE" in h["issuer"]


def test_compute_smart_money_holder_has_issuer(tmp_path, monkeypatch):
    """Each holder entry must carry a non-empty 'issuer' field (E2.5 fix)."""
    import engine.smart_money as _sm

    monkeypatch.setattr(_sm.config, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(_sm.config, "load", lambda: {"smart_money": {"funds": {}}})

    snap_dir = tmp_path / "smart_money" / "issuerfund"
    snap_dir.mkdir(parents=True)
    snap = pd.DataFrame([
        {"cusip": "MSF001", "issuer": "MICROSOFT CORP", "sh_type": "SH",
         "shares": 999.0, "value_usd": 370_000.0,
         "fund_slug": "issuerfund", "period_end": "2025-12-31", "filing_date": "2026-02-14"},
    ])
    snap.to_parquet(snap_dir / "2025-12-31.parquet")

    # _norm("MICROSOFT CORP") = "MICROSOFT"
    monkeypatch.setattr(_sm, "name_ticker_map", lambda *a, **kw: {"MICROSOFT": "MSFT"})
    monkeypatch.setattr(_sm, "full_cusip_map", lambda *a, **kw: ({"MSF001": "MSFT"}, {"openfigi_entries": 0, "ark_seed_entries": 0}))
    monkeypatch.setattr(_sm, "_accumulation", lambda *a, **kw: {})
    monkeypatch.setattr(_sm, "_safe_manager_quality", lambda *a, **kw: {})

    result = _sm.compute_smart_money({
        "panel_top_n": 12,
        "funds": {"issuerfund": {"name": "Issuer Fund"}},
    })
    assert result is not None
    holders = result["by_ticker"]["MSFT"]["holders"]
    assert holders[0]["issuer"] != "", "issuer must be non-empty string (E2.5 fix)"
    assert "MICROSOFT" in holders[0]["issuer"]


# --------------------------------------------------------------------------- #
# days_to_exit computes from fixture holder shares + ADV                        #
# --------------------------------------------------------------------------- #

def test_days_to_exit_from_holder_shares():
    """days_to_exit = agg_shares / ADV, computed from holder records carrying 'shares'."""
    from engine.ownership_crowding import days_to_exit, adv_shares

    # Synthetic holder rows with shares populated
    holders = [
        {"action": "hold", "shares": 1_000_000.0, "value_usd": 150_000_000.0},
        {"action": "add",  "shares": 500_000.0,  "value_usd":  75_000_000.0},
        {"action": "exit", "shares": 200_000.0,  "value_usd":       0.0},  # excluded
    ]
    non_exit = [h for h in holders if h.get("action") != "exit"]
    agg_shares = sum(float(h.get("shares") or 0) for h in non_exit)
    assert agg_shares == pytest.approx(1_500_000.0)

    # With ADV = 500_000, dte = 1_500_000 / 500_000 = 3.0
    dte = days_to_exit(agg_shares=agg_shares, adv=500_000.0)
    assert dte == pytest.approx(3.0, abs=0.05)
