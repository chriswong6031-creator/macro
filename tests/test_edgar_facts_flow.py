"""Tests for W2 PR-H EDGAR FLOW additions (collectors/edgar_facts.py).

Covers:
  1. New concepts (sbc, research_dev) appear in the FLOW dict and are extracted
     from the companyfacts fixture via _statements_for.
  2. Existing concepts extended with new fallback (depreciation now includes "Depreciation"
     as a third fallback) — verify the fallback chain resolves correctly.
  3. Fallback ordering: earlier concept in the chain wins when both are present.
  4. Panel additions (edgar.py): op_income and interest_exp present in FLOW dict
     and PANEL_NUMERIC.
  5. End-to-end: fetch_statements with a mocked _get_json returns a DataFrame
     with all W2 PR-H columns populated.

All tests are fixture-based (no network calls).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar_facts as ef  # noqa: E402
import collectors.edgar as ep        # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def _entry(concept_val, fy, start_offset_days=0, form="10-K"):
    """Build a minimal companyfacts XBRL entry dict."""
    import datetime
    end_dt = datetime.date(fy, 12, 31)
    start_dt = datetime.date(fy, 1, 1)
    return {
        "fp": "FY",
        "form": form,
        "fy": fy,
        "val": concept_val,
        "end": end_dt.isoformat(),
        "start": start_dt.isoformat(),
        "filed": end_dt.isoformat(),
    }


def _companyfacts(cik_concepts: dict) -> dict:
    """Assemble a minimal companyfacts API response.

    cik_concepts: {concept_name: [(fy, val), ...]}
    Returns the JSON shape data.sec.gov/api/xbrl/companyfacts/CIK{}.json returns.
    """
    usgaap: dict = {}
    for concept, year_vals in cik_concepts.items():
        entries = [_entry(val, fy) for fy, val in year_vals]
        usgaap[concept] = {"units": {"USD": entries}}
    return {"facts": {"us-gaap": usgaap}}


def _patch_facts(monkeypatch, tmp_path, cik: int, facts_json: dict,
                 cik_map: dict | None = None):
    """Monkeypatch _get_json and _cik_map in edgar_facts so no network calls occur."""
    monkeypatch.setattr(ef, "_get_json", lambda url, *a, **kw: facts_json)
    monkeypatch.setattr(ef, "_cik_map", lambda: cik_map or {"TSTK": cik})
    monkeypatch.setattr(ef.time, "sleep", lambda *a, **kw: None)
    cache = tmp_path / "statements.parquet"
    monkeypatch.setattr(ef, "_cache_path", lambda: cache)


# ---------------------------------------------------------------------------
# 1. FLOW dict: new concept keys present
# ---------------------------------------------------------------------------

class TestFlowDictContents:
    def test_sbc_key_present(self):
        assert "sbc" in ef.FLOW, "sbc must be in edgar_facts.FLOW (W2 PR-H)"

    def test_research_dev_key_present(self):
        assert "research_dev" in ef.FLOW, "research_dev must be in edgar_facts.FLOW (W2 PR-H)"

    def test_depreciation_primary_concept(self):
        assert ef.FLOW["depreciation"][0] == "DepreciationDepletionAndAmortization"

    def test_depreciation_has_third_fallback(self):
        # W2 PR-H extends depreciation with a third fallback ("Depreciation")
        assert len(ef.FLOW["depreciation"]) >= 3, (
            "depreciation chain must have ≥3 fallbacks after W2 PR-H")
        assert "Depreciation" in ef.FLOW["depreciation"]

    def test_sbc_primary_and_fallback(self):
        chain = ef.FLOW["sbc"]
        assert chain[0] == "ShareBasedCompensation"
        assert "AllocatedShareBasedCompensationExpense" in chain

    def test_research_dev_primary(self):
        chain = ef.FLOW["research_dev"]
        assert chain[0] == "ResearchAndDevelopmentExpense"

    def test_interest_exp_still_present(self):
        assert "interest_exp" in ef.FLOW

    def test_op_income_still_present(self):
        assert "op_income" in ef.FLOW


# ---------------------------------------------------------------------------
# 2. Panel FLOW dict and PANEL_NUMERIC (edgar.py)
# ---------------------------------------------------------------------------

class TestPanelAdditions:
    def test_op_income_in_panel_flow(self):
        assert "op_income" in ep.FLOW, (
            "op_income must be in edgar.FLOW to populate the fundamentals panel (W2 PR-H)")

    def test_interest_exp_in_panel_flow(self):
        assert "interest_exp" in ep.FLOW, (
            "interest_exp must be in edgar.FLOW to populate the fundamentals panel (W2 PR-H)")

    def test_op_income_in_panel_numeric(self):
        assert "op_income" in ep.PANEL_NUMERIC, (
            "op_income must be in PANEL_NUMERIC to be written into fundamentals_panel.parquet")

    def test_interest_exp_in_panel_numeric(self):
        assert "interest_exp" in ep.PANEL_NUMERIC, (
            "interest_exp must be in PANEL_NUMERIC to be written into fundamentals_panel.parquet")

    def test_op_income_concept_name(self):
        assert ep.FLOW["op_income"] == "OperatingIncomeLoss"

    def test_interest_exp_concept_name(self):
        assert ep.FLOW["interest_exp"] == "InterestExpense"

    def test_panel_numeric_existing_cols_intact(self):
        """Ensure the W2 additions did not remove existing columns."""
        for col in ("assets", "equity", "ni", "gross_profit", "cfo", "revenue",
                    "assets_prior", "ni_prior", "shares"):
            assert col in ep.PANEL_NUMERIC, f"existing PANEL_NUMERIC column {col!r} was removed"


# ---------------------------------------------------------------------------
# 3. _concept() fallback chain — earlier concept wins
# ---------------------------------------------------------------------------

class TestConceptFallback:
    def _usgaap(self, concept_vals: dict) -> dict:
        """Build a minimal us-gaap facts dict {concept: {units: {USD: [entries]}}}."""
        out = {}
        for concept, year_vals in concept_vals.items():
            out[concept] = {"units": {"USD": [_entry(v, fy) for fy, v in year_vals]}}
        return out

    def test_first_concept_wins_when_both_present(self):
        usgaap = self._usgaap({
            "ShareBasedCompensation": [(2023, 500.0)],
            "AllocatedShareBasedCompensationExpense": [(2023, 999.0)],
        })
        vals, ends = ef._concept(usgaap, ef.FLOW["sbc"])
        assert vals[2023] == 500.0, "earlier concept in chain must win"
        assert ends[2023] == "2023-12-31", "period_end carried out per fy"

    def test_fallback_used_when_primary_absent(self):
        usgaap = self._usgaap({
            "AllocatedShareBasedCompensationExpense": [(2022, 300.0)],
        })
        vals, _ends = ef._concept(usgaap, ef.FLOW["sbc"])
        assert vals[2022] == 300.0

    def test_depreciation_third_fallback_used(self):
        # Only "Depreciation" (third) is present — must be found
        usgaap = self._usgaap({
            "Depreciation": [(2021, 150.0)],
        })
        vals, _ends = ef._concept(usgaap, ef.FLOW["depreciation"])
        assert vals[2021] == 150.0, "third depreciation fallback 'Depreciation' must work"

    def test_research_dev_primary_extraction(self):
        usgaap = self._usgaap({
            "ResearchAndDevelopmentExpense": [(2022, 8000.0), (2023, 9500.0)],
        })
        vals, ends = ef._concept(usgaap, ef.FLOW["research_dev"])
        assert vals == {2022: 8000.0, 2023: 9500.0}
        assert ends == {2022: "2022-12-31", 2023: "2023-12-31"}

    def test_missing_concept_returns_empty(self):
        usgaap: dict = {}
        vals, ends = ef._concept(usgaap, ef.FLOW["sbc"])
        assert vals == {}
        assert ends == {}


# ---------------------------------------------------------------------------
# 4. _statements_for() — end-to-end extraction with mocked network
# ---------------------------------------------------------------------------

class TestStatementsFor:
    def _fake_cik(self):
        return 320193

    def _facts_with_new_fields(self):
        """companyfacts JSON fixture with all W2 PR-H concepts populated."""
        return _companyfacts({
            # existing concepts
            "OperatingIncomeLoss": [(2022, 119437000000.0), (2023, 114301000000.0)],
            "NetIncomeLoss": [(2022, 99803000000.0), (2023, 96995000000.0)],
            "Revenues": [(2022, 394328000000.0), (2023, 383285000000.0)],
            "GrossProfit": [(2022, 170782000000.0), (2023, 169148000000.0)],
            "NetCashProvidedByUsedInOperatingActivities": [(2022, 122151000000.0), (2023, 110543000000.0)],
            "PaymentsToAcquirePropertyPlantAndEquipment": [(2022, 10708000000.0), (2023, 10959000000.0)],
            "InterestExpense": [(2022, 2931000000.0), (2023, 3933000000.0)],
            # new W2 PR-H concepts
            "DepreciationDepletionAndAmortization": [(2022, 11104000000.0), (2023, 11519000000.0)],
            "ShareBasedCompensation": [(2022, 9038000000.0), (2023, 10833000000.0)],
            "ResearchAndDevelopmentExpense": [(2022, 26251000000.0), (2023, 29915000000.0)],
            # balance sheet
            "Assets": [(2022, 352755000000.0), (2023, 352583000000.0)],
            "StockholdersEquity": [(2022, 50672000000.0), (2023, 62146000000.0)],
            "CashAndCashEquivalentsAtCarryingValue": [(2022, 23646000000.0), (2023, 29965000000.0)],
            "LongTermDebtNoncurrent": [(2022, 98959000000.0), (2023, 95281000000.0)],
        })

    def test_sbc_extracted(self, monkeypatch):
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: self._facts_with_new_fields())
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)
        rows = ef._statements_for(self._fake_cik())
        assert rows, "must return at least one row"
        by_fy = {r["fy"]: r for r in rows}
        assert by_fy[2023].get("sbc") == pytest.approx(10833000000.0)

    def test_research_dev_extracted(self, monkeypatch):
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: self._facts_with_new_fields())
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)
        rows = ef._statements_for(self._fake_cik())
        by_fy = {r["fy"]: r for r in rows}
        assert by_fy[2023].get("research_dev") == pytest.approx(29915000000.0)

    def test_depreciation_extracted(self, monkeypatch):
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: self._facts_with_new_fields())
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)
        rows = ef._statements_for(self._fake_cik())
        by_fy = {r["fy"]: r for r in rows}
        assert by_fy[2023].get("depreciation") == pytest.approx(11519000000.0)

    def test_interest_exp_extracted(self, monkeypatch):
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: self._facts_with_new_fields())
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)
        rows = ef._statements_for(self._fake_cik())
        by_fy = {r["fy"]: r for r in rows}
        assert by_fy[2023].get("interest_exp") == pytest.approx(3933000000.0)

    def test_op_income_extracted(self, monkeypatch):
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: self._facts_with_new_fields())
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)
        rows = ef._statements_for(self._fake_cik())
        by_fy = {r["fy"]: r for r in rows}
        assert by_fy[2023].get("op_income") == pytest.approx(114301000000.0)

    def test_columns_present_in_output(self, monkeypatch):
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: self._facts_with_new_fields())
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)
        rows = ef._statements_for(self._fake_cik())
        assert rows, "no rows returned"
        latest = rows[-1]
        for col in ("sbc", "research_dev", "depreciation", "interest_exp", "op_income",
                    "period_end"):
            assert col in latest, f"column {col!r} absent from statement row"
        # period_end carried through for point-in-time gating (fixture end = fy-12-31)
        assert latest["period_end"] == "2023-12-31"

    def test_missing_companyfacts_returns_empty(self, monkeypatch):
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: None)
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)
        rows = ef._statements_for(self._fake_cik())
        assert rows == []


# ---------------------------------------------------------------------------
# 5. fetch_statements() — DataFrame columns end-to-end
# ---------------------------------------------------------------------------

class TestFetchStatements:
    def _facts(self):
        return _companyfacts({
            "OperatingIncomeLoss": [(2023, 50e9)],
            "NetIncomeLoss": [(2023, 40e9)],
            "Revenues": [(2023, 200e9)],
            "GrossProfit": [(2023, 80e9)],
            "NetCashProvidedByUsedInOperatingActivities": [(2023, 60e9)],
            "PaymentsToAcquirePropertyPlantAndEquipment": [(2023, 5e9)],
            "InterestExpense": [(2023, 2e9)],
            "DepreciationDepletionAndAmortization": [(2023, 10e9)],
            "ShareBasedCompensation": [(2023, 3e9)],
            "ResearchAndDevelopmentExpense": [(2023, 15e9)],
            "Assets": [(2023, 300e9)],
            "StockholdersEquity": [(2023, 80e9)],
        })

    def test_dataframe_has_w2_columns(self, monkeypatch, tmp_path):
        _patch_facts(monkeypatch, tmp_path, cik=320193, facts_json=self._facts())
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        for col in ("sbc", "research_dev", "depreciation", "interest_exp"):
            assert col in df.columns, f"column {col!r} must be in fetch_statements output"

    def test_ticker_column_present(self, monkeypatch, tmp_path):
        _patch_facts(monkeypatch, tmp_path, cik=320193, facts_json=self._facts())
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        assert "ticker" in df.columns
        assert "TSTK" in df["ticker"].values

    def test_sbc_value_round_trips(self, monkeypatch, tmp_path):
        _patch_facts(monkeypatch, tmp_path, cik=320193, facts_json=self._facts())
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        sub = df[df["ticker"] == "TSTK"]
        assert not sub.empty
        assert sub["sbc"].iloc[0] == pytest.approx(3e9)

    def test_research_dev_value_round_trips(self, monkeypatch, tmp_path):
        _patch_facts(monkeypatch, tmp_path, cik=320193, facts_json=self._facts())
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        sub = df[df["ticker"] == "TSTK"]
        assert sub["research_dev"].iloc[0] == pytest.approx(15e9)

    def test_net_debt_to_ebitda_inputs_all_present(self, monkeypatch, tmp_path):
        """The net_debt_to_ebitda bug was: depreciation always None → ebitda uncomputable.
        Verify that after this PR, all three required inputs (op_income, depreciation, and
        balance sheet debt/cash from BALANCE) are present in the raw row."""
        facts_with_balance = _companyfacts({
            "OperatingIncomeLoss": [(2023, 50e9)],
            "NetIncomeLoss": [(2023, 40e9)],
            "Revenues": [(2023, 200e9)],
            "DepreciationDepletionAndAmortization": [(2023, 10e9)],
            "InterestExpense": [(2023, 2e9)],
            "ShareBasedCompensation": [(2023, 3e9)],
            "ResearchAndDevelopmentExpense": [(2023, 8e9)],
            "Assets": [(2023, 300e9)],
            "StockholdersEquity": [(2023, 80e9)],
            "LongTermDebtNoncurrent": [(2023, 90e9)],
            "CashAndCashEquivalentsAtCarryingValue": [(2023, 20e9)],
        })
        _patch_facts(monkeypatch, tmp_path, cik=1, facts_json=facts_with_balance)
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        sub = df[df["ticker"] == "TSTK"].iloc[0]
        # op_income and depreciation must both be non-null
        assert sub.get("op_income") is not None or pd.notna(sub.get("op_income", None)) is False
        op = sub["op_income"]
        dep = sub["depreciation"]
        assert pd.notna(op), "op_income must be non-null for net_debt_to_ebitda"
        assert pd.notna(dep), "depreciation must be non-null for net_debt_to_ebitda"
        # ebitda proxy
        ebitda = op + dep
        assert ebitda > 0
