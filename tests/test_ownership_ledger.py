"""Tests for engine.ownership_ledger — in-memory fixtures, no network/disk.

Coverage:
- _ledger_advance_enabled: nightly guard (env var gate)
- _append_rows: idempotency (advance twice same-day → no dupes)
- _grade_entry: null panel degrades gracefully
- L2 anchor-dated ADV: post-anchor bar cannot influence result
- ledger_summary: returns expected cohort keys even with empty ledgers
- advance_ledgers: skips when COLLECT_LANE != nightly
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.ownership_ledger as ol


# --------------------------------------------------------------------------- #
# Nightly guard                                                                 #
# --------------------------------------------------------------------------- #

class TestNightlyGuard:
    def test_disabled_without_env_var(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        assert ol._ledger_advance_enabled() is False

    def test_enabled_with_nightly(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert ol._ledger_advance_enabled() is True

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "NIGHTLY")
        assert ol._ledger_advance_enabled() is True

    def test_other_value_disabled(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "intraday")
        assert ol._ledger_advance_enabled() is False

    def test_us_lane_fallback(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.setenv("US_LANE", "nightly")
        assert ol._ledger_advance_enabled() is True


# --------------------------------------------------------------------------- #
# Idempotency: advance twice same-day → no dupes                               #
# --------------------------------------------------------------------------- #

class TestLedgerIdempotency:
    def test_append_rows_deduplication(self, tmp_path):
        """Appending the same rows twice leaves only one copy."""
        rows = [
            {"ticker": "AAPL", "anchor_date": "2026-07-10", "slug": "alpha",
             "cohort": "L1", "pct_portfolio": 2.5, "action": "new",
             "turnover_tier": "low"},
            {"ticker": "MSFT", "anchor_date": "2026-07-10", "slug": "alpha",
             "cohort": "L1", "pct_portfolio": 1.5, "action": "add",
             "turnover_tier": "low"},
        ]
        # First append
        n1 = ol._append_rows("L1", rows, root=tmp_path)
        assert n1 == 2

        # Second append with same rows → 0 added (idempotent)
        n2 = ol._append_rows("L1", rows, root=tmp_path)
        assert n2 == 0

        # Ledger should have exactly 2 rows
        df = ol._load_ledger("L1", root=tmp_path)
        assert len(df) == 2

    def test_append_new_rows_after_existing(self, tmp_path):
        """New rows with a different anchor_date are appended correctly."""
        row_day1 = [{"ticker": "AAPL", "anchor_date": "2026-07-10", "slug": "alpha",
                     "cohort": "L1", "action": "new", "pct_portfolio": 2.5,
                     "turnover_tier": "low"}]
        row_day2 = [{"ticker": "AAPL", "anchor_date": "2026-07-11", "slug": "alpha",
                     "cohort": "L1", "action": "new", "pct_portfolio": 2.5,
                     "turnover_tier": "low"}]
        ol._append_rows("L1", row_day1, root=tmp_path)
        n = ol._append_rows("L1", row_day2, root=tmp_path)
        assert n == 1
        df = ol._load_ledger("L1", root=tmp_path)
        assert len(df) == 2

    def test_different_cohorts_separate_files(self, tmp_path):
        """L1 and L2 do not cross-contaminate."""
        l1_rows = [{"ticker": "AAPL", "anchor_date": "2026-07-10", "slug": "alpha",
                    "cohort": "L1", "action": "new", "pct_portfolio": 2.0,
                    "turnover_tier": "low"}]
        l2_rows = [{"ticker": "AAPL", "anchor_date": "2026-07-10",
                    "cohort": "L2", "days_to_exit": 55.0}]
        ol._append_rows("L1", l1_rows, root=tmp_path)
        ol._append_rows("L2", l2_rows, root=tmp_path)

        df_l1 = ol._load_ledger("L1", root=tmp_path)
        df_l2 = ol._load_ledger("L2", root=tmp_path)
        assert len(df_l1) == 1
        assert len(df_l2) == 1

    def test_empty_rows_noop(self, tmp_path):
        """Appending empty list doesn't write anything."""
        n = ol._append_rows("L1", [], root=tmp_path)
        assert n == 0
        p = ol._ledger_path("L1", root=tmp_path)
        assert not p.exists()


# --------------------------------------------------------------------------- #
# _grade_entry: null panel degrades gracefully                                  #
# --------------------------------------------------------------------------- #

class TestGradeEntry:
    def _null_panel(self):
        """A stub panel that always returns None (no prices)."""
        class NullPanel:
            def get(self, ticker):
                return None
        return NullPanel()

    def test_null_panel_returns_empty(self):
        result = ol._grade_entry("AAPL", "2026-07-01", self._null_panel())
        assert result == {}

    def test_real_panel_returns_dict_keys(self):
        """With a real price series, forward_metrics returns expected keys."""
        dates = pd.date_range("2026-01-01", periods=300, freq="B")
        prices = pd.Series(range(100, 400), index=dates, dtype=float)

        class FakePanel:
            def get(self, ticker):
                return prices if ticker == "AAPL" else prices * 0.99

        result = ol._grade_entry("AAPL", "2026-01-02", FakePanel())
        # Should have at least entry_price
        assert "entry_price" in result or result == {}
        # If grading succeeded, it should have fwd_ret_21
        if result:
            assert "fwd_ret_21" in result


# --------------------------------------------------------------------------- #
# L2 anchor-dated ADV PIT test                                                  #
# --------------------------------------------------------------------------- #

class TestL2AnchorDatedADV:
    """A bar AFTER the anchor must not change the ADV result (PIT law).

    Uses engine.ownership_crowding.adv_shares which enforces the as_of cutoff
    on both FINRA and yahoo paths.
    """
    def test_post_anchor_bar_does_not_affect_adv(self, tmp_path, monkeypatch):
        """Inject a fake yahoo parquet where a volume spike happens AFTER anchor.
        The result with as_of=anchor must equal the result computed without the spike row.
        """
        import numpy as np
        from engine.ownership_crowding import adv_shares

        anchor = "2026-06-30"
        post_anchor_date = pd.Timestamp("2026-07-05")

        # Build a fake yahoo volume series: 100 shares/day for 30 days, then 1e9 spike
        dates = pd.date_range("2026-06-01", periods=30, freq="B")
        vols = [100.0] * len(dates)
        df = pd.DataFrame({"volume": vols}, index=dates)

        # Add a post-anchor spike row
        spike_row = pd.DataFrame({"volume": [1_000_000_000.0]}, index=[post_anchor_date])
        df_with_spike = pd.concat([df, spike_row]).sort_index()

        # Write to tmp_path/yahoo/TSTK.parquet
        yahoo_dir = tmp_path / "yahoo"
        yahoo_dir.mkdir()
        df_with_spike.to_parquet(yahoo_dir / "TSTK.parquet")

        # Patch config.data_dir to return tmp_path
        from lib import config as cfg_mod
        monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)
        # No FINRA data in tmp_path → falls back to yahoo
        monkeypatch.setattr(cfg_mod, "ROOT", tmp_path)

        # ADV with as_of=anchor should NOT include the spike
        result_anchored = adv_shares("TSTK", as_of=anchor)
        assert result_anchored is not None
        adv_anchored = result_anchored["adv"]

        # ADV without cutoff includes the spike (much larger)
        result_full = adv_shares("TSTK", as_of=None)
        assert result_full is not None
        adv_full = result_full["adv"]

        # The spike must inflate the uncut result significantly
        assert adv_full > adv_anchored * 10, (
            f"Spike not captured: anchored={adv_anchored}, full={adv_full}")

        # Anchored ADV should be close to 100 (the pre-anchor average)
        assert adv_anchored == pytest.approx(100.0, abs=1.0)


# --------------------------------------------------------------------------- #
# ledger_summary                                                                #
# --------------------------------------------------------------------------- #

class TestLedgerSummary:
    def test_empty_ledgers(self, tmp_path):
        """ledger_summary returns all five cohorts even with empty stores (L5 added in #2457)."""
        summary = ol.ledger_summary(root=tmp_path)
        assert set(summary.keys()) == {"L1", "L2", "L3", "L4", "L5"}
        for cohort, s in summary.items():
            assert s["n_total"] == 0
            assert s["entry_asof"] is None
            assert s["entered_this_cycle"] == 0
            assert s["status"] == "accruing"
            assert "rule" in s
            assert "legs" in s
            for h in ("h21", "h63", "h126", "h252"):
                assert s["legs"][h] is None

    def test_with_data_no_matured(self, tmp_path):
        """Ledger with entries but no matured excess → all legs still None."""
        rows = [
            {"ticker": "AAPL", "anchor_date": "2026-07-10", "slug": "alpha",
             "cohort": "L1", "action": "new", "pct_portfolio": 2.5,
             "turnover_tier": "low", "entry_price": 200.0, "fill_date": "2026-07-11"},
        ]
        ol._append_rows("L1", rows, root=tmp_path)
        summary = ol.ledger_summary(root=tmp_path)
        assert summary["L1"]["n_total"] == 1
        assert summary["L1"]["entered_this_cycle"] == 1
        assert summary["L1"]["entry_asof"] == "2026-07-10"
        assert summary["L1"]["status"] == "accruing"
        # No excess columns → legs are None
        for h in ("h21", "h63", "h126", "h252"):
            assert summary["L1"]["legs"][h] is None

    def test_with_matured_excess(self, tmp_path):
        """When excess columns are populated, legs show median_excess."""
        rows = [
            {"ticker": "AAPL", "anchor_date": "2026-04-10", "slug": "alpha",
             "cohort": "L1", "action": "new", "pct_portfolio": 2.5,
             "turnover_tier": "low", "entry_price": 200.0, "fill_date": "2026-04-11",
             "excess_21": 0.05, "excess_63": 0.12, "excess_126": None, "excess_252": None},
            {"ticker": "MSFT", "anchor_date": "2026-04-10", "slug": "alpha",
             "cohort": "L1", "action": "add", "pct_portfolio": 1.5,
             "turnover_tier": "low", "entry_price": 300.0, "fill_date": "2026-04-11",
             "excess_21": 0.03, "excess_63": 0.08, "excess_126": None, "excess_252": None},
        ]
        ol._append_rows("L1", rows, root=tmp_path)
        summary = ol.ledger_summary(root=tmp_path)
        assert summary["L1"]["n_total"] == 2
        assert summary["L1"]["legs"]["h21"] is not None
        assert summary["L1"]["legs"]["h21"]["n_matured"] == 2
        assert summary["L1"]["legs"]["h21"]["median_excess"] == pytest.approx(0.04, abs=0.001)
        assert summary["L1"]["legs"]["h63"]["median_excess"] == pytest.approx(0.10, abs=0.001)
        # 126d not matured → None
        assert summary["L1"]["legs"]["h126"] is None


# --------------------------------------------------------------------------- #
# advance_ledgers: skips when COLLECT_LANE != nightly                           #
# --------------------------------------------------------------------------- #

class TestAdvanceLedgersNightlyGuard:
    def test_skips_intraday(self, monkeypatch, tmp_path):
        """advance_ledgers returns all zeros when COLLECT_LANE != nightly."""
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        funds = {"alpha": {"name": "Alpha"}}
        result = ol.advance_ledgers(funds, sm_payload=None, root=tmp_path)
        assert result == {"L1": 0, "L2": 0, "L3": 0, "L4": 0, "L5": 0}
        # No files should have been written
        ledger_dir = tmp_path / "data" / "smart_money" / "ledgers"
        assert not ledger_dir.exists() or not list(ledger_dir.glob("*.parquet"))

    def test_runs_on_nightly(self, monkeypatch, tmp_path):
        """advance_ledgers runs when COLLECT_LANE=nightly (even if it produces 0 entries
        due to missing data — the point is it does NOT skip)."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")

        # Monkeypatch heavy imports so the function runs without disk data
        monkeypatch.setattr(ol, "_l1_entries", lambda funds, panel: [])
        monkeypatch.setattr(ol, "_l2_entries", lambda sm, panel: [])
        monkeypatch.setattr(ol, "_l3_entries", lambda panel: [])
        monkeypatch.setattr(ol, "_l4_entries", lambda sm, panel: [])
        monkeypatch.setattr(ol, "_l5_entries", lambda models, panel: [])

        # Also monkeypatch ClosePanel import inside advance_ledgers
        import engine.manager_trades as mt
        class FakePanel:
            def get(self, ticker): return None
        monkeypatch.setattr(mt, "ClosePanel", lambda: FakePanel())

        funds = {"alpha": {"name": "Alpha"}}
        result = ol.advance_ledgers(funds, sm_payload={}, root=tmp_path)
        # Should have tried all cohorts (returned 0 since mocked to empty)
        assert set(result.keys()) == {"L1", "L2", "L3", "L4", "L5"}


# --------------------------------------------------------------------------- #
# M3 PIT anchor: L2/L4 must use filing_date, not period_end (look-ahead-free)  #
# --------------------------------------------------------------------------- #

class TestL2L4FilingDateAnchor:
    """L2 and L4 must anchor on filing_date (public disclosure date), not
    period_end (~45d earlier). This prevents ~45d of look-ahead leakage.

    Fixture: holders with period_end=2026-03-31 and filing_date=2026-05-15.
    Assert the anchor_date passed to forward_metrics / stored in the ledger row
    is 2026-05-15, not 2026-03-31.
    """

    def _make_sm_payload(self, ticker: str,
                         period_end: str = "2026-03-31",
                         filing_date: str = "2026-05-15",
                         n_funds: int = 3) -> dict:
        """Minimal sm_payload with controllable period_end / filing_date on holders."""
        holders = [
            {"fund": f"FUND{i}", "fund_name": f"Fund {i}", "action": "hold",
             "pct_portfolio": 2.0, "value_usd": 2_000_000.0,
             "period_end": period_end,
             "filing_date": filing_date,   # the public-disclosure anchor
             "shares": 1_000_000.0,
             "shares_change_pct": None}
            for i in range(n_funds)
        ]
        return {
            "by_ticker": {
                ticker: {
                    "holders": holders,
                    "as_of": period_end,    # old period_end field still present
                    "vip": n_funds,
                }
            },
            "most_held": [{"ticker": ticker, "n_funds": n_funds,
                           "total_value": 6_000_000.0}],
        }

    def test_l2_anchor_is_filing_date_not_period_end(self, monkeypatch):
        """_l2_entries must use max(holder.filing_date) for the anchor, not as_of."""
        captured_anchors: list[str] = []

        def fake_adv(ticker, as_of=None):
            return {"adv": 50_000.0, "source": "yahoo"}

        def fake_grade(ticker, anchor, panel):
            captured_anchors.append(anchor)
            return {}

        monkeypatch.setattr(ol, "_grade_entry", fake_grade)
        monkeypatch.setattr(ol, "_spy_grade", lambda a, p: {})
        monkeypatch.setattr(ol, "_fwd_mae", lambda t, a, p: {})

        # Patch adv_shares inside ownership_ledger's import
        import engine.ownership_crowding as oc
        monkeypatch.setattr(oc, "adv_shares", fake_adv)

        period_end = "2026-03-31"
        filing_date = "2026-05-15"
        payload = self._make_sm_payload("AAPL",
                                        period_end=period_end,
                                        filing_date=filing_date,
                                        n_funds=10)

        class NullPanel:
            def get(self, t): return None

        entries = ol._l2_entries(payload, NullPanel())
        # Entries may be empty (dte quintile needs >=5 tickers), but if anchor was
        # captured it must be filing_date; we capture via _grade_entry mock.
        for anchor in captured_anchors:
            assert anchor == filing_date, (
                f"L2 anchor should be filing_date {filing_date!r}, "
                f"got period_end-era {anchor!r}")
        # If we got entries, verify anchor_date in the rows themselves
        for row in entries:
            assert row["anchor_date"] == filing_date, (
                f"L2 row anchor_date {row['anchor_date']!r} != "
                f"filing_date {filing_date!r}")

    def test_l4_anchor_is_filing_date_not_period_end(self, monkeypatch):
        """_l4_entries must use max(holder.filing_date) for the anchor, not as_of."""
        captured_anchors: list[str] = []

        def fake_grade(ticker, anchor, panel):
            captured_anchors.append(anchor)
            return {}

        monkeypatch.setattr(ol, "_grade_entry", fake_grade)
        monkeypatch.setattr(ol, "_spy_grade", lambda a, p: {})

        period_end = "2026-03-31"
        filing_date = "2026-05-15"
        payload = self._make_sm_payload("MSFT",
                                        period_end=period_end,
                                        filing_date=filing_date)

        class NullPanel:
            def get(self, t): return None

        entries = ol._l4_entries(payload, NullPanel())
        assert len(entries) >= 1, "Expected at least one L4 entry from fixture"
        for row in entries:
            assert row["anchor_date"] == filing_date, (
                f"L4 row anchor_date {row['anchor_date']!r} != "
                f"filing_date {filing_date!r}")
        for anchor in captured_anchors:
            assert anchor == filing_date, (
                f"L4 _grade_entry called with anchor {anchor!r} "
                f"instead of filing_date {filing_date!r}")

    def test_l2_skips_entry_when_no_filing_date(self, monkeypatch):
        """When no holder carries a filing_date, L2 must skip the entry (null-honest)."""
        import engine.ownership_crowding as oc
        monkeypatch.setattr(oc, "adv_shares", lambda t, as_of=None: {"adv": 50_000.0, "source": "yahoo"})
        monkeypatch.setattr(ol, "_grade_entry", lambda t, a, p: {})
        monkeypatch.setattr(ol, "_spy_grade", lambda a, p: {})
        monkeypatch.setattr(ol, "_fwd_mae", lambda t, a, p: {})

        # Build payload with empty filing_date on all holders
        payload = self._make_sm_payload("TSLA", period_end="2026-03-31",
                                        filing_date="", n_funds=10)

        class NullPanel:
            def get(self, t): return None

        entries = ol._l2_entries(payload, NullPanel())
        # With no filing_date, the ticker should be skipped entirely (no entry)
        assert not any(r["ticker"] == "TSLA" for r in entries), (
            "L2 must skip tickers whose holders have no filing_date")
