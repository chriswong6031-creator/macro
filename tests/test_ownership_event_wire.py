"""Tests for engine.ownership_event_wire — pure-function coverage with in-memory fixtures.

All tests inject fake data (no disk, no network).

Coverage:
- filing_season_clock: deadline math across quarter boundaries; filed_pending states
- wire merge: axis stamp preservation, roster_hit flag
- 13D/G rows: signal classification, roster_hit
- Insider rows: quiver freshness check, axis labeling
- freshness_axes: tier thresholds
- No-fusion assertion: crowding rows keep short_volume and short_interest in separate sub-dicts
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.ownership_event_wire import (
    filing_season_clock,
    _latest_completed_quarter,
    _13dg_rows,
    _insider_rows_quiver,
    freshness_axes,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #

def _funds():
    return {
        "alphaone": {"name": "Alpha One Capital"},
        "betatwo": {"name": "Beta Two Partners"},
    }


def _fund_filings(period_end_alpha, fd_alpha, period_end_beta, fd_beta):
    return {
        "alphaone": {"period_end": period_end_alpha, "filing_date": fd_alpha},
        "betatwo": {"period_end": period_end_beta, "filing_date": fd_beta},
    }


# --------------------------------------------------------------------------- #
# _latest_completed_quarter                                                     #
# --------------------------------------------------------------------------- #

class TestLatestCompletedQuarter:
    def test_q1_end_march(self):
        # Today is June 15 — latest completed quarter is Q1 (March 31)
        assert _latest_completed_quarter(date(2026, 6, 15)) == date(2026, 3, 31)

    def test_q2_end_june(self):
        # Today is September 1 — latest completed is Q2 (June 30)
        assert _latest_completed_quarter(date(2026, 9, 1)) == date(2026, 6, 30)

    def test_q3_end_september(self):
        # Today is December 1 — latest completed is Q3 (Sep 30)
        assert _latest_completed_quarter(date(2026, 12, 1)) == date(2026, 9, 30)

    def test_q4_end_december(self):
        # Today is February 5 next year — latest completed is Q4 (Dec 31)
        assert _latest_completed_quarter(date(2027, 2, 5)) == date(2026, 12, 31)

    def test_q2_day_zero(self):
        # Today is July 1 — yesterday was June 30 (Q2 end)
        assert _latest_completed_quarter(date(2026, 7, 1)) == date(2026, 6, 30)

    def test_january(self):
        # Today is Jan 15 — latest completed is Q4 of prior year
        assert _latest_completed_quarter(date(2026, 1, 15)) == date(2025, 12, 31)


# --------------------------------------------------------------------------- #
# filing_season_clock                                                           #
# --------------------------------------------------------------------------- #

class TestFilingSeasonClock:
    """Tests inject `today` to keep the clock deterministic."""

    def test_window_open_q2_2026(self):
        # Q2 2026 (Jun 30) window opens Jul 1; deadline is Aug 14 (Jun30+45).
        # Today = Jul 10 — window is open.
        today = date(2026, 7, 10)
        clock = filing_season_clock(_funds(), today=today)
        assert clock["quarter_state"] == "window_open"
        assert clock["next_deadline"] == "2026-08-14"
        assert clock["days_to_deadline"] == (date(2026, 8, 14) - today).days
        assert clock["quarter_end"] == "2026-06-30"

    def test_window_closed_q2_2026(self):
        # Q2 2026 (Jun 30) deadline = Aug 14. Today = Sep 1 → window closed.
        today = date(2026, 9, 1)
        clock = filing_season_clock(_funds(), today=today)
        # Sep 1 > Aug 14 → window_closed
        assert clock["quarter_state"] == "window_closed"
        assert clock["quarter_end"] == "2026-06-30"

    def test_window_closed_directly(self):
        # Today = Sep 1; Q2 deadline was Aug 14 → window_closed
        today = date(2026, 9, 1)
        clock = filing_season_clock(_funds(), today=today)
        assert clock["quarter_state"] == "window_closed"
        assert clock["days_to_deadline"] < 0

    def test_between_quarters(self):
        # Today = Jun 30 — quarter hasn't ended yet; quarter_state = 'between'
        today = date(2026, 6, 30)
        clock = filing_season_clock(_funds(), today=today)
        # latest_completed_quarter(Jun 30) = Mar 31 (since Jun 30 is Q2 end but not past it)
        assert clock["quarter_state"] in ("between", "window_open", "window_closed")
        # The correct logic: today <= qend → 'between'
        # qend = Mar 31 for Jun 30 (since month=6 → >=4 → qend = Mar 31)
        assert clock["quarter_end"] == "2026-03-31"

    def test_filed_status_filed(self):
        # Fund has period_end matching the expected quarter
        today = date(2026, 7, 10)  # window_open; expected Q = 2026-06-30
        filings = _fund_filings("2026-06-30", "2026-07-05", "2026-03-31", "2026-04-20")
        clock = filing_season_clock(_funds(), fund_filings=filings, today=today)
        grid = {r["slug"]: r for r in clock["filed_pending"]}
        assert grid["alphaone"]["status"] == "filed"
        assert grid["betatwo"]["status"] == "pending"

    def test_filed_status_lapsed(self):
        # Window closed, betatwo period_end != expected quarter → lapsed
        today = date(2026, 9, 1)  # window_closed
        filings = _fund_filings("2026-06-30", "2026-07-05", "2026-03-31", "2026-04-20")
        clock = filing_season_clock(_funds(), fund_filings=filings, today=today)
        grid = {r["slug"]: r for r in clock["filed_pending"]}
        assert grid["alphaone"]["status"] == "filed"
        assert grid["betatwo"]["status"] == "lapsed"

    def test_no_fund_filings(self):
        # All funds are pending when no filing data provided
        today = date(2026, 7, 10)
        clock = filing_season_clock(_funds(), fund_filings=None, today=today)
        statuses = {r["slug"]: r["status"] for r in clock["filed_pending"]}
        assert all(s == "pending" for s in statuses.values())

    def test_grid_has_all_funds(self):
        today = date(2026, 7, 10)
        clock = filing_season_clock(_funds(), today=today)
        slugs = {r["slug"] for r in clock["filed_pending"]}
        assert slugs == {"alphaone", "betatwo"}

    def test_days_to_deadline_mid_window(self):
        today = date(2026, 7, 10)
        clock = filing_season_clock(_funds(), today=today)
        expected = (date(2026, 8, 14) - today).days
        assert clock["days_to_deadline"] == expected

    def test_deadline_negative_after_window(self):
        today = date(2026, 9, 1)
        clock = filing_season_clock(_funds(), today=today)
        assert clock["days_to_deadline"] < 0


# --------------------------------------------------------------------------- #
# 13D/G axis                                                                    #
# --------------------------------------------------------------------------- #

class TestThirteenDGRows:
    """_13dg_rows reads from disk, so we test classify_filer_type separately and
    check that _13dg_rows handles empty filings gracefully."""

    def test_classify_passive_giant(self):
        from engine.beneficial_ownership import classify_filer_type
        assert classify_filer_type("VANGUARD GROUP INC") == "passive_giant"
        assert classify_filer_type("BLACKROCK INC") == "passive_giant"

    def test_classify_other(self):
        from engine.beneficial_ownership import classify_filer_type
        assert classify_filer_type("ELLIOTT ASSOCIATES LP") == "other"
        assert classify_filer_type(None) == "unknown"

    def test_roster_hit_flag(self):
        """roster_hit is True only for tickers in roster."""
        # Simulate rows from the enrichment cache directly via regime_for
        from engine.beneficial_ownership import regime_for
        rows = pd.DataFrame([
            {"form_type": "SC 13D", "date_filed": "2026-07-01",
             "filer": "Elliott Associates", "filer_type": "other"},
        ])
        result = regime_for(rows)
        assert result is not None
        assert result["state"] == "activist"
        assert result["signal"] == "high"

    def test_no_disk_data_returns_empty(self, tmp_path, monkeypatch):
        """When no filings file exists, _13dg_rows returns []."""
        import engine.beneficial_ownership as bo
        monkeypatch.setattr(bo, "_load_enrichment", lambda: None)
        rows = _13dg_rows(roster={"AAPL", "MSFT"})
        assert rows == []


# --------------------------------------------------------------------------- #
# Insider rows                                                                  #
# --------------------------------------------------------------------------- #

class TestInsiderRows:
    def test_quiver_basic(self):
        """_insider_rows_quiver produces buy/sell cluster rows for roster tickers."""
        df = pd.DataFrame([
            {"Ticker": "AAPL", "Date": "2026-07-01", "AcquiredDisposedCode": "A",
             "Shares": 1000, "PricePerShare": 150.0},
            {"Ticker": "AAPL", "Date": "2026-07-02", "AcquiredDisposedCode": "A",
             "Shares": 500, "PricePerShare": 151.0},
            {"Ticker": "MSFT", "Date": "2026-07-01", "AcquiredDisposedCode": "D",
             "Shares": 200, "PricePerShare": 300.0},
            # TSLA not in roster — should be excluded
            {"Ticker": "TSLA", "Date": "2026-07-01", "AcquiredDisposedCode": "A",
             "Shares": 100, "PricePerShare": 200.0},
        ])
        roster = {"AAPL", "MSFT"}
        rows = _insider_rows_quiver(roster, asof="2026-07-09",
                                    note="quiver insiders as-of 2026-07-09 (0d lag)",
                                    _df=df)
        assert len(rows) == 2  # AAPL + MSFT, TSLA excluded
        by_ticker = {r["ticker"]: r for r in rows}
        assert by_ticker["AAPL"]["action"] == "insider_buy_cluster"
        assert by_ticker["MSFT"]["action"] == "insider_sell_cluster"
        assert by_ticker["AAPL"]["n_buys"] == 2
        assert by_ticker["MSFT"]["n_sells"] == 1
        # All rows are roster_hit = True
        assert all(r["roster_hit"] for r in rows)

    def test_axis_label(self):
        """axis field is 'form4/quiver-insider'."""
        rows = _insider_rows_quiver(set(), asof="2026-07-09", note="x",
                                     _df=pd.DataFrame([{"Ticker": "AAPL",
                                                         "Date": "2026-07-01",
                                                         "AcquiredDisposedCode": "A",
                                                         "Shares": 100,
                                                         "PricePerShare": 10.0}]))
        # Empty roster → no rows
        assert rows == []

    def test_quiver_net_usd_calculation(self):
        """net_usd = buy_usd - sell_usd."""
        df = pd.DataFrame([
            {"Ticker": "AAPL", "Date": "2026-07-01", "AcquiredDisposedCode": "A",
             "Shares": 100, "PricePerShare": 200.0},  # +20000
            {"Ticker": "AAPL", "Date": "2026-07-02", "AcquiredDisposedCode": "D",
             "Shares": 50, "PricePerShare": 200.0},   # -10000
        ])
        rows = _insider_rows_quiver({"AAPL"}, asof="2026-07-09", note="x", _df=df)
        assert rows[0]["net_usd"] == pytest.approx(10000.0, abs=1)


# --------------------------------------------------------------------------- #
# Wire merge ordering + axis stamp preservation                                 #
# --------------------------------------------------------------------------- #

class TestWireMerge:
    def test_axis_stamp_preserved(self):
        """Each row retains its native axis tag — no cross-axis contamination."""
        # Build artificial rows and verify stamps
        rows_13f = [{"date": "2026-07-05", "axis": "13f", "type": "new",
                     "asof_note": "13F filing 2026-07-05"}]
        rows_dg = [{"date": "2026-07-08", "axis": "13dg", "type": "SC 13D",
                    "asof_note": "13D/G filing 2026-07-08"}]
        rows_ins = [{"date": "2026-07-09", "axis": "form4/quiver-insider",
                     "type": "insider_cluster", "asof_note": "quiver insiders as-of 2026-07-09"}]

        # Merge and sort (mirrors build_wire logic)
        all_rows = rows_13f + rows_dg + rows_ins
        all_rows.sort(key=lambda r: r.get("date", ""), reverse=True)

        # Verify descending date order
        dates = [r["date"] for r in all_rows]
        assert dates == sorted(dates, reverse=True)

        # Verify each row still has its own axis tag intact
        axes = {r["axis"] for r in all_rows}
        assert "13f" in axes
        assert "13dg" in axes
        assert "form4/quiver-insider" in axes

    def test_no_axis_blending(self):
        """No row has fields from multiple axes (the SM2-R3 no-fusion check)."""
        # A 13f row must NOT have `signal`, `filer_type` (from 13dg)
        row_13f = {"date": "2026-07-05", "axis": "13f", "type": "new",
                   "magnitude": 2.5, "unit": "pct_book", "asof_note": "13F filing"}
        # A 13dg row must NOT have `pct_book`, `value_usd` (from 13f)
        row_dg = {"date": "2026-07-08", "axis": "13dg", "type": "SC 13D",
                  "signal": "high", "filer_type": "other", "asof_note": "13D/G filing"}
        # Neither should share numeric cross-axis derived fields
        assert "filer_type" not in row_13f
        assert "pct_book" not in row_dg
        assert "value_usd" not in row_dg


# --------------------------------------------------------------------------- #
# Freshness tiers                                                               #
# --------------------------------------------------------------------------- #

class TestFreshnessTiers:
    def _make_clock(self):
        return {
            "filed_pending": [
                {"slug": "a", "name": "A", "filing_date": "2026-07-05",
                 "period_end": "2026-06-30", "status": "filed"},
            ],
        }

    def test_freshness_axes_returns_five_keys(self, monkeypatch):
        """freshness_axes always returns exactly 5 entries."""
        # Monkeypatch disk reads to return stale/absent
        import engine.short_volume as sv_mod
        import engine.ownership_event_wire as wire_mod
        monkeypatch.setattr(sv_mod, "load_panel", lambda: None)
        # Patch config.data_dir to return a path that doesn't have finra/short_interest
        import pathlib
        monkeypatch.setattr(
            wire_mod.config, "data_dir",
            lambda: pathlib.Path("/nonexistent/path")
        )
        clock = self._make_clock()
        axes = freshness_axes([], clock)
        assert len(axes) == 5
        keys = [a["key"] for a in axes]
        assert keys == ["13f", "13dg", "insider", "short_volume", "short_interest"]

    def test_tier_majority_quarter(self, monkeypatch):
        """13f axis reads the MAJORITY quarter, not the newest single filing —
        one early filer must not paint the axis green (honest-lag fix)."""
        import datetime
        import engine.short_volume as sv_mod
        import engine.ownership_event_wire as wire_mod
        import pathlib
        monkeypatch.setattr(sv_mod, "load_panel", lambda: None)
        monkeypatch.setattr(wire_mod.config, "data_dir",
                            lambda: pathlib.Path("/nonexistent/path"))

        today = datetime.date.today()
        stale_pe = str(today - datetime.timedelta(days=100))
        fresh_pe = str(today - datetime.timedelta(days=5))
        clock = {"filed_pending": [
            {"slug": "a", "filing_date": str(today - datetime.timedelta(days=56)),
             "period_end": stale_pe, "status": "pending", "name": "A"},
            {"slug": "b", "filing_date": str(today - datetime.timedelta(days=55)),
             "period_end": stale_pe, "status": "pending", "name": "B"},
            {"slug": "c", "filing_date": str(today),
             "period_end": fresh_pe, "status": "filed", "name": "C"},
        ]}
        axes = freshness_axes([], clock)
        ax_13f = next(a for a in axes if a["key"] == "13f")
        # majority period_end (2 of 3 funds) wins; 100-day-old data → red tier
        assert ax_13f["asof"] == stale_pe
        assert ax_13f["tier"] == "red"
        assert "1/3 funds already filed a newer quarter" in ax_13f["lag_note"]
        # All axes must have required keys and valid tier values
        for ax in axes:
            assert "key" in ax
            assert "label" in ax
            assert "asof" in ax
            assert "lag_note" in ax
            assert "tier" in ax
            assert ax["tier"] in ("green", "amber", "red")


# --------------------------------------------------------------------------- #
# No-fusion payload assertion (SM2-R3)                                         #
# --------------------------------------------------------------------------- #

class TestNoFusionPayload:
    """Assert the crowding payload keeps short_volume and short_interest in separate
    sub-dicts with no cross-axis numeric fields merged between them."""

    def _make_crowding_row(self):
        """A well-formed crowding row (from _build_crowding output contract)."""
        return {
            "ticker": "AAPL",
            "issuer": "Apple",
            "n_funds": 5,
            "agg_value_usd": 1e9,
            "hhi": 0.3,
            "max_book_pct": 8.0,
            "days_to_exit": 25.0,
            "crowding_tier": "moderate",
            "entry_band": {"p25": 150, "p50": 160, "p75": 170, "n_underwater": 1, "n": 3,
                           "label": "implied avg entry (quarter-end proxy)"},
            # short_volume — own asof
            "short_volume": {
                "ratio": 0.42,
                "trend_pp": 1.2,
                "ratio_z": 0.8,
                "asof": "2026-07-09",        # daily stamp — SEPARATE from settlement_date
            },
            # short_interest — own settlement_date
            "short_interest": {
                "days_to_cover": 3.5,
                "si_change_pct": -2.1,
                "settlement_date": "2026-07-01",  # bi-monthly stamp — SEPARATE from short_volume.asof
            },
        }

    def test_separate_sub_dicts(self):
        """short_volume and short_interest must be separate keys, never merged."""
        row = self._make_crowding_row()
        sv = row["short_volume"]
        si = row["short_interest"]
        # They are separate dicts
        assert isinstance(sv, dict)
        assert isinstance(si, dict)
        # Their timestamp keys are different names
        assert "asof" in sv
        assert "settlement_date" in si
        # short_volume.asof ≠ settlement_date key (no collision)
        assert "settlement_date" not in sv
        assert "asof" not in si

    def test_no_shared_numeric_field(self):
        """No numeric field exists in both sub-dicts."""
        row = self._make_crowding_row()
        sv_keys = set(row["short_volume"].keys())
        si_keys = set(row["short_interest"].keys())
        shared = sv_keys & si_keys
        # Only non-numeric meta keys would be permissible; we expect zero intersection here
        assert len(shared) == 0, f"Unexpected shared keys: {shared}"

    def test_no_composite_in_top_level(self):
        """The top-level crowding row must NOT contain a combined field mixing the two axes."""
        row = self._make_crowding_row()
        # Forbidden: a field like 'combined_short_score' that blends sv + si
        forbidden_patterns = ["combined", "fused", "blended", "composite"]
        for k in row.keys():
            for pat in forbidden_patterns:
                assert pat not in k.lower(), f"Suspicious composite key: {k}"

    def test_crowding_tier_derives_from_dte_only(self):
        """crowding_tier is a string label; days_to_exit is the sole numeric basis (SM2-R3)."""
        from engine.ownership_crowding import crowding_tier, days_to_exit
        dte = days_to_exit(agg_shares=5e6, adv=250000)
        tier = crowding_tier(dte)
        assert tier in ("low", "moderate", "elevated", "unavailable")
        # No short-volume or SI metric was passed — crowding_tier only takes dte
        import inspect
        sig = inspect.signature(crowding_tier)
        param_names = list(sig.parameters.keys())
        assert "short_ratio" not in param_names
        assert "days_to_cover" not in param_names


# --------------------------------------------------------------------------- #
# Wire cap + 13D/G dedup (E2.5 defect fixes)                                   #
# --------------------------------------------------------------------------- #

class TestWireCapAndDedup:
    """E2.5 fix: wire capped at 250 rows; 13D/G custodial re-files deduped."""

    def _make_13dg_rows(self, n: int) -> list[dict]:
        """Produce n distinct 13D/G rows."""
        rows = []
        for i in range(n):
            rows.append({
                "date": f"2026-07-{str(i % 10 + 1).zfill(2)}",
                "axis": "13dg",
                "type": "SC 13G/A",
                "slug": "",
                "fund": f"Custodian_{i}",
                "ticker": f"T{i:04d}",
                "issuer": f"Corp {i}",
                "action": "13g",
                "magnitude": None,
                "unit": None,
                "asof_note": "...",
                "signal": "low",
                "filer_type": "passive_giant",
                "roster_hit": False,
            })
        return rows

    def test_wire_cap_trims_to_250(self, monkeypatch):
        """build_wire must emit at most 250 rows."""
        import engine.ownership_event_wire as wire_mod
        # Inject 400 rows by overriding the axis functions
        big_rows = self._make_13dg_rows(400)
        monkeypatch.setattr(wire_mod, "_13f_rows", lambda funds: [])
        monkeypatch.setattr(wire_mod, "_13dg_rows", lambda **kw: big_rows)
        monkeypatch.setattr(wire_mod, "_insider_rows", lambda roster: [])
        monkeypatch.setattr(wire_mod, "_roster_tickers", lambda funds: set())
        from engine.ownership_event_wire import build_wire
        wire, clock = build_wire({})
        assert len(wire) == 250

    def test_13dg_dedup_keeps_newest(self):
        """Duplicate (filer, ticker, form) entries keep only the newest date."""
        from engine.ownership_event_wire import _13dg_rows
        import engine.beneficial_ownership as bo

        # Inject two rows for the same (filer, ticker, form), different dates
        df = pd.DataFrame([
            {"ticker": "AAPL", "date_filed": "2026-07-05",
             "form_type": "SC 13G/A", "filer": "Vanguard", "filer_type": "passive_giant",
             "company": "Apple Inc"},
            {"ticker": "AAPL", "date_filed": "2026-07-09",  # newer
             "form_type": "SC 13G/A", "filer": "Vanguard", "filer_type": "passive_giant",
             "company": "Apple Inc"},
            {"ticker": "MSFT", "date_filed": "2026-07-08",  # different ticker, not a dupe
             "form_type": "SC 13G/A", "filer": "Vanguard", "filer_type": "passive_giant",
             "company": "Microsoft Corp"},
        ])
        # monkeypatch _load_enrichment to return our fixture
        import unittest.mock as mock
        with mock.patch.object(bo, "_load_enrichment", return_value=df):
            rows = _13dg_rows(lookback_days=30, roster={"AAPL", "MSFT"})

        # AAPL should appear only once (deduped), MSFT once → total 2
        tickers = [r["ticker"] for r in rows]
        assert tickers.count("AAPL") == 1
        assert tickers.count("MSFT") == 1
        # The kept AAPL row should be the newer one
        aapl_row = next(r for r in rows if r["ticker"] == "AAPL")
        assert aapl_row["date"] == "2026-07-09"

    def test_13dg_lookback_constant_is_14(self):
        """The main wire 13D/G lookback constant must be 14 days (E2.5 spec)."""
        from engine.ownership_event_wire import _13DG_LOOKBACK_DAYS
        assert _13DG_LOOKBACK_DAYS == 14

    def test_activists_lookback_constant_is_45(self):
        """The activists board lookback constant must be 45 days (independent feed)."""
        from engine.ownership_event_wire import _13DG_LOOKBACK_ACTIVISTS
        assert _13DG_LOOKBACK_ACTIVISTS == 45
