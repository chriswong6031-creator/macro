"""Tests for LHB-R6 quarterly-store enrichment (scripts/backfill_edgar_quarterly.py).

LHB-R6 (2026-07-12) adds four working-capital balance sheet fields to the quarterly
EDGAR store: receivables, inventory, payables, contract_liabilities.

Test coverage:
  (a) Each new field extracts from its primary tag at quarterly instants.
  (b) Fallback chain order is respected (e.g. ContractWithCustomerLiabilityCurrent
      preferred over DeferredRevenue when both are present).
  (c) A filer with none of the new tags yields NaN/None without error.
  (d) Merge path: existing parquet WITHOUT the new columns + fresh rows WITH them
      → combined frame has the columns, old rows NaN (no KeyError).
  (e) The four chains for receivables/inventory equal the annual collectors/edgar_facts.py
      chains exactly (sync guard — annual chains are authoritative).

All tests are fixture-based — no network calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scripts.backfill_edgar_quarterly as bq   # noqa: E402
import collectors.edgar_facts as ef              # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _q_instant_entry(val: float, fy: int, fq: int, form: str = "10-Q",
                     filed: str | None = None) -> dict:
    """Minimal XBRL instant entry for a quarterly balance-sheet concept."""
    fp = f"Q{fq}"
    end = f"{fy}-{fq * 3:02d}-30"
    return {
        "fp": fp,
        "form": form,
        "fy": fy,
        "val": val,
        "end": end,
        "filed": filed or end,
    }


def _usgaap_with(*concept_entry_pairs: tuple[str, list[dict]]) -> dict:
    """Build a minimal us-gaap dict from (concept_name, [entries]) pairs."""
    usgaap: dict = {}
    for concept, entries in concept_entry_pairs:
        usgaap[concept] = {"units": {"USD": entries}}
    return usgaap


# ---------------------------------------------------------------------------
# (a) Primary tag extraction for each new field
# ---------------------------------------------------------------------------

class TestPrimaryTagExtraction:
    """Each new LHB-R6 field extracts its value from the primary tag."""

    def _extract_series(self, concept: str, val: float = 1_000_000.0) -> dict:
        """Run _concept_q for a single primary tag, return the (fy, fq) → dict map."""
        usgaap = _usgaap_with(
            (concept, [_q_instant_entry(val, 2024, 1)]),
        )
        return bq._concept_q(usgaap, [concept], unit="USD", instant=True)

    def test_receivables_primary_tag(self):
        primary = bq.BALANCE_WORKINGCAP_Q["receivables"][0]
        assert primary == "AccountsReceivableNetCurrent"
        series = self._extract_series(primary, val=5_000_000.0)
        assert (2024, 1) in series, "Q1 2024 must be extracted via primary receivables tag"
        assert series[(2024, 1)]["val"] == pytest.approx(5_000_000.0)

    def test_inventory_primary_tag(self):
        primary = bq.BALANCE_WORKINGCAP_Q["inventory"][0]
        assert primary == "InventoryNet"
        series = self._extract_series(primary, val=2_500_000.0)
        assert (2024, 1) in series, "Q1 2024 must be extracted via primary inventory tag"
        assert series[(2024, 1)]["val"] == pytest.approx(2_500_000.0)

    def test_payables_primary_tag(self):
        primary = bq.BALANCE_WORKINGCAP_Q["payables"][0]
        assert primary == "AccountsPayableCurrent"
        series = self._extract_series(primary, val=3_000_000.0)
        assert (2024, 1) in series, "Q1 2024 must be extracted via primary payables tag"
        assert series[(2024, 1)]["val"] == pytest.approx(3_000_000.0)

    def test_contract_liabilities_primary_tag(self):
        primary = bq.BALANCE_WORKINGCAP_Q["contract_liabilities"][0]
        assert primary == "ContractWithCustomerLiabilityCurrent"
        series = self._extract_series(primary, val=750_000.0)
        assert (2024, 1) in series, (
            "Q1 2024 must be extracted via primary contract_liabilities tag")
        assert series[(2024, 1)]["val"] == pytest.approx(750_000.0)

    def test_new_fields_in_output_rows(self, monkeypatch):
        """End-to-end: _statements_quarterly() returns all four new columns."""
        usgaap = _usgaap_with(
            ("AccountsReceivableNetCurrent", [_q_instant_entry(1e6, 2024, 1)]),
            ("InventoryNet", [_q_instant_entry(2e6, 2024, 1)]),
            ("AccountsPayableCurrent", [_q_instant_entry(3e6, 2024, 1)]),
            ("ContractWithCustomerLiabilityCurrent", [_q_instant_entry(4e6, 2024, 1)]),
        )
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(bq, "_get_json", lambda *a, **kw: facts)
        monkeypatch.setattr(bq.time, "sleep", lambda *a, **kw: None)

        rows = bq._statements_quarterly(cik=12345, ua="test-agent")
        assert rows, "must return at least one row"
        row = rows[0]
        assert row.get("receivables") == pytest.approx(1e6), "receivables must be populated"
        assert row.get("inventory") == pytest.approx(2e6), "inventory must be populated"
        assert row.get("payables") == pytest.approx(3e6), "payables must be populated"
        assert row.get("contract_liabilities") == pytest.approx(4e6), (
            "contract_liabilities must be populated")


# ---------------------------------------------------------------------------
# (b) Fallback chain order respected
# ---------------------------------------------------------------------------

class TestFallbackChainOrder:
    """Primary concept wins when multiple tags in the chain are present."""

    def test_contract_liabilities_primary_wins_over_deferred_revenue(self):
        """ContractWithCustomerLiabilityCurrent must win over DeferredRevenue."""
        primary = "ContractWithCustomerLiabilityCurrent"
        fallback = "DeferredRevenue"
        usgaap = _usgaap_with(
            (primary, [_q_instant_entry(100_000.0, 2024, 2)]),
            (fallback, [_q_instant_entry(999_999.0, 2024, 2)]),
        )
        chain = bq.BALANCE_WORKINGCAP_Q["contract_liabilities"]
        series = bq._concept_q(usgaap, chain, unit="USD", instant=True)
        # Primary wins: _concept_q uses setdefault so the first populated concept
        # in the chain wins for any given (fy, fq) key.
        assert (2024, 2) in series
        assert series[(2024, 2)]["val"] == pytest.approx(100_000.0), (
            f"Primary tag {primary!r} must win over fallback {fallback!r}")

    def test_contract_liabilities_fallback_used_when_primary_absent(self):
        """DeferredRevenueCurrent is used when primary tags are absent."""
        usgaap = _usgaap_with(
            ("DeferredRevenueCurrent", [_q_instant_entry(55_000.0, 2024, 3)]),
        )
        chain = bq.BALANCE_WORKINGCAP_Q["contract_liabilities"]
        series = bq._concept_q(usgaap, chain, unit="USD", instant=True)
        assert (2024, 3) in series
        assert series[(2024, 3)]["val"] == pytest.approx(55_000.0), (
            "DeferredRevenueCurrent fallback must be used when primary tags absent")

    def test_payables_primary_wins_over_trade_current(self):
        """AccountsPayableCurrent wins over AccountsPayableTradeCurrent."""
        usgaap = _usgaap_with(
            ("AccountsPayableCurrent", [_q_instant_entry(200_000.0, 2024, 1)]),
            ("AccountsPayableTradeCurrent", [_q_instant_entry(300_000.0, 2024, 1)]),
        )
        chain = bq.BALANCE_WORKINGCAP_Q["payables"]
        series = bq._concept_q(usgaap, chain, unit="USD", instant=True)
        assert (2024, 1) in series
        assert series[(2024, 1)]["val"] == pytest.approx(200_000.0), (
            "AccountsPayableCurrent must win over AccountsPayableTradeCurrent")

    def test_receivables_primary_wins_over_receivables_net(self):
        """AccountsReceivableNetCurrent wins over ReceivablesNetCurrent."""
        usgaap = _usgaap_with(
            ("AccountsReceivableNetCurrent", [_q_instant_entry(400_000.0, 2024, 1)]),
            ("ReceivablesNetCurrent", [_q_instant_entry(500_000.0, 2024, 1)]),
        )
        chain = bq.BALANCE_WORKINGCAP_Q["receivables"]
        series = bq._concept_q(usgaap, chain, unit="USD", instant=True)
        assert (2024, 1) in series
        assert series[(2024, 1)]["val"] == pytest.approx(400_000.0), (
            "AccountsReceivableNetCurrent must win over ReceivablesNetCurrent")


# ---------------------------------------------------------------------------
# (c) Filer with none of the new tags yields NaN/None without error
# ---------------------------------------------------------------------------

class TestMissingTagsYieldNaN:
    """A filer that tags none of the four LHB-R6 concepts gets NaN, no KeyError."""

    def test_no_new_tags_no_error(self, monkeypatch):
        """A filer with only revenue tagged (no working-capital tags) succeeds."""
        usgaap = _usgaap_with(
            ("Revenues", [_q_instant_entry(10e6, 2024, 1)]),
        )
        # Make Revenues a flow concept (has start date)
        flow_entry = {
            "fp": "Q1", "form": "10-Q", "fy": 2024,
            "val": 10e6, "start": "2024-01-01", "end": "2024-03-31",
            "filed": "2024-04-15",
        }
        usgaap["Revenues"] = {"units": {"USD": [flow_entry]}}
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(bq, "_get_json", lambda *a, **kw: facts)
        monkeypatch.setattr(bq.time, "sleep", lambda *a, **kw: None)

        rows = bq._statements_quarterly(cik=99999, ua="test-agent")
        assert rows, "must return rows even with no working-capital tags"
        row = rows[0]
        # All four new fields must be None (not KeyError)
        for field in ("receivables", "inventory", "payables", "contract_liabilities"):
            assert row.get(field) is None, (
                f"field {field!r} must be None when no corresponding tag is present")

    def test_empty_usgaap_returns_no_rows(self, monkeypatch):
        """An entirely empty us-gaap section returns [] without error."""
        facts = {"facts": {"us-gaap": {}}}
        monkeypatch.setattr(bq, "_get_json", lambda *a, **kw: facts)
        monkeypatch.setattr(bq.time, "sleep", lambda *a, **kw: None)

        rows = bq._statements_quarterly(cik=1, ua="test-agent")
        assert rows == [], "empty us-gaap must return empty list"


# ---------------------------------------------------------------------------
# (d) Merge path: existing parquet WITHOUT new columns + fresh rows WITH them
# ---------------------------------------------------------------------------

class TestMergeColumnSuperset:
    """pd.concat of column-subset existing + column-superset fresh fills NaN cleanly."""

    def test_old_rows_get_nan_for_new_columns(self, tmp_path):
        """Existing parquet without LHB-R6 columns gets NaN filled after concat."""
        # Build an "old" store without the four new columns
        old_data = {
            "ticker": ["AAPL", "AAPL"],
            "fiscal_year": [2023, 2022],
            "fiscal_quarter": [1, 1],
            "revenue": [100e9, 90e9],
            "filed": ["2023-04-15", "2022-04-15"],
            "as_of": ["2023-01-01", "2022-01-01"],
        }
        old_df = pd.DataFrame(old_data)
        old_path = tmp_path / "statements_quarterly.parquet"
        old_df.to_parquet(old_path, index=False)

        # "Fresh" rows WITH the new LHB-R6 columns (simulating a new backfill for MSFT)
        fresh_data = {
            "ticker": ["MSFT"],
            "fiscal_year": [2024],
            "fiscal_quarter": [1],
            "revenue": [60e9],
            "filed": ["2024-04-25"],
            "as_of": ["2024-01-01"],
            "receivables": [5e9],
            "inventory": [1e8],
            "payables": [3e9],
            "contract_liabilities": [2e9],
        }
        fresh_df = pd.DataFrame(fresh_data)

        # Simulate the merge path in run()
        existing = pd.read_parquet(old_path)
        # fresh is for a different ticker so existing is kept as-is
        refreshed_tickers = fresh_df["ticker"].unique()
        existing_kept = existing[~existing["ticker"].isin(refreshed_tickers)]
        combined = pd.concat([existing_kept, fresh_df], ignore_index=True)

        # The combined frame must have the new columns
        for col in ("receivables", "inventory", "payables", "contract_liabilities"):
            assert col in combined.columns, f"combined frame must have column {col!r}"

        # Old AAPL rows must have NaN for the new columns (not KeyError)
        aapl_rows = combined[combined["ticker"] == "AAPL"]
        for col in ("receivables", "inventory", "payables", "contract_liabilities"):
            assert aapl_rows[col].isna().all(), (
                f"AAPL rows (pre-LHB-R6) must have NaN for {col!r}")

        # MSFT row must have actual values
        msft_row = combined[combined["ticker"] == "MSFT"].iloc[0]
        assert msft_row["receivables"] == pytest.approx(5e9)
        assert msft_row["inventory"] == pytest.approx(1e8)
        assert msft_row["payables"] == pytest.approx(3e9)
        assert msft_row["contract_liabilities"] == pytest.approx(2e9)

    def test_combined_frame_round_trips_parquet(self, tmp_path):
        """Combined frame with NaN in new columns writes and re-reads without error."""
        old_df = pd.DataFrame({
            "ticker": ["X"], "fiscal_year": [2020], "fiscal_quarter": [1],
            "revenue": [1e9], "filed": ["2020-04-01"], "as_of": ["2020-01-01"],
        })
        fresh_df = pd.DataFrame({
            "ticker": ["Y"], "fiscal_year": [2024], "fiscal_quarter": [1],
            "revenue": [2e9], "filed": ["2024-04-01"], "as_of": ["2024-01-01"],
            "receivables": [500e6], "inventory": [100e6],
            "payables": [300e6], "contract_liabilities": [50e6],
        })
        combined = pd.concat([old_df, fresh_df], ignore_index=True)
        out = tmp_path / "test_combined.parquet"
        combined.to_parquet(out, index=False)

        reread = pd.read_parquet(out)
        assert len(reread) == 2
        x_row = reread[reread["ticker"] == "X"].iloc[0]
        for col in ("receivables", "inventory", "payables", "contract_liabilities"):
            assert pd.isna(x_row[col]), f"X row must have NaN for {col!r} after parquet round-trip"


# ---------------------------------------------------------------------------
# (e) Sync guard: receivables/inventory chains must match annual edgar_facts.py
# ---------------------------------------------------------------------------

class TestAnnualChainSync:
    """LHB-R6 receivables and inventory chains must match collectors/edgar_facts.py BALANCE.

    The annual collector's chains are authoritative per LHB-R6 spec. This test
    enforces tag consistency so both stores can be compared without tag mismatch.
    """

    def test_receivables_chain_matches_annual(self):
        annual_chain = ef.BALANCE["receivables"]
        quarterly_chain = bq.BALANCE_WORKINGCAP_Q["receivables"]
        assert quarterly_chain == annual_chain, (
            f"receivables chain MISMATCH.\n"
            f"  Annual (edgar_facts.py):    {annual_chain}\n"
            f"  Quarterly (backfill_edgar_quarterly.py): {quarterly_chain}\n"
            "Annual chains are authoritative per LHB-R6. Update quarterly to match."
        )

    def test_inventory_chain_matches_annual(self):
        annual_chain = ef.BALANCE["inventory"]
        quarterly_chain = bq.BALANCE_WORKINGCAP_Q["inventory"]
        assert quarterly_chain == annual_chain, (
            f"inventory chain MISMATCH.\n"
            f"  Annual (edgar_facts.py):    {annual_chain}\n"
            f"  Quarterly (backfill_edgar_quarterly.py): {quarterly_chain}\n"
            "Annual chains are authoritative per LHB-R6. Update quarterly to match."
        )

    def test_payables_exists_in_quarterly_not_annual(self):
        """payables is a NEW quarterly field — it must be present in quarterly store
        but is not required to exist in the annual BALANCE dict (different scope)."""
        assert "payables" in bq.BALANCE_WORKINGCAP_Q, (
            "payables must be in BALANCE_WORKINGCAP_Q (LHB-R6)")
        # payables may or may not be in annual BALANCE — we don't assert either way.

    def test_contract_liabilities_exists_in_quarterly(self):
        """contract_liabilities is a NEW quarterly field per LHB-R6."""
        assert "contract_liabilities" in bq.BALANCE_WORKINGCAP_Q, (
            "contract_liabilities must be in BALANCE_WORKINGCAP_Q (LHB-R6)")


# ---------------------------------------------------------------------------
# (f) fp="FY" year-end instants are EXCLUDED (safer false-negative, never a
#     contaminated Q4 value) — same behavior as cash/debt/shares instants.
# ---------------------------------------------------------------------------
class TestFyInstantExcluded:
    def test_fy_tagged_instant_is_dropped(self, monkeypatch):
        fy_entry = _q_instant_entry(9e6, 2024, 4, form="10-K")
        fy_entry["fp"] = "FY"  # year-end balance tagged FY, not Q4
        q3_entry = _q_instant_entry(5e6, 2024, 3)
        usgaap = _usgaap_with(
            ("AccountsReceivableNetCurrent", [fy_entry, q3_entry]),
        )
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(bq, "_get_json", lambda *a, **kw: facts)
        monkeypatch.setattr(bq.time, "sleep", lambda *a, **kw: None)
        rows = bq._statements_quarterly(cik=7, ua="test-agent")
        by_q = {(r["fiscal_year"], r["fiscal_quarter"]): r for r in rows}
        assert (2024, 3) in by_q and by_q[(2024, 3)]["receivables"] == pytest.approx(5e6)
        q4 = by_q.get((2024, 4))
        assert q4 is None or q4.get("receivables") in (None, float("nan")) or pd.isna(q4.get("receivables")), (
            "fp=FY instant must NOT populate Q4 receivables"
        )
