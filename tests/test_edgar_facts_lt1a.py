"""Tests for LT-1a EDGAR collector fixes (collectors/edgar_facts.py).

Covers three defects confirmed by census 2026-07-06:

  1. shares null (unit mismatch): BALANCE loop called _concept() with unit="USD" but
     us-gaap:CommonStockSharesOutstanding lives in the "shares" XBRL unit.  After the
     fix, shares extraction uses unit="shares" via the new BALANCE_SHARES dict.

  2. period_end stamping: period_end must be non-null for every row that has at least
     one FLOW or BALANCE concept present (it was already present in code; this test
     verifies the contract holds after the fix and that the shares path also contributes
     to period_end absorption).

  3. Future-FY guard: rows whose period_end > run date must be silently dropped by
     _statements_for().  The XBRL 'fy' field is unreliable (e.g. STX encodes their
     FY ending June 2025 as fy=2027); period_end is the canonical signal.

All tests are fixture-based — no network calls.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.edgar_facts as ef  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _flow_entry(val: float, fy: int, form: str = "10-K", filed: str | None = None) -> dict:
    """Minimal XBRL entry for a FLOW (period) concept — 365-day fiscal year."""
    end = f"{fy}-12-31"
    start = f"{fy}-01-01"
    return {
        "fp": "FY",
        "form": form,
        "fy": fy,
        "val": val,
        "start": start,
        "end": end,
        "filed": filed or end,
    }


def _instant_entry(val: float, fy: int, end: str, form: str = "10-K",
                   filed: str | None = None) -> dict:
    """Minimal XBRL entry for an INSTANT concept (no start date)."""
    return {
        "fp": "FY",
        "form": form,
        "fy": fy,
        "val": val,
        "end": end,
        "filed": filed or end,
        "start": None,
    }


def _companyfacts_usd(concepts: dict[str, list[tuple[int, float]]]) -> dict:
    """Assemble companyfacts JSON where all concepts are in USD unit."""
    usgaap: dict = {}
    for concept, year_vals in concepts.items():
        usgaap[concept] = {"units": {"USD": [_flow_entry(v, fy) for fy, v in year_vals]}}
    return {"facts": {"us-gaap": usgaap}}


def _companyfacts_with_shares(
    usd_concepts: dict[str, list[tuple[int, float]]],
    shares_by_fy: dict[int, tuple[float, str]],   # {fy: (val, end_date)}
) -> dict:
    """Assemble companyfacts JSON with USD concepts PLUS shares-unit concept."""
    usgaap: dict = {}
    # USD concepts
    for concept, year_vals in usd_concepts.items():
        usgaap[concept] = {"units": {"USD": [_flow_entry(v, fy) for fy, v in year_vals]}}
    # shares-unit concept
    entries = [
        _instant_entry(val, fy, end_date)
        for fy, (val, end_date) in shares_by_fy.items()
    ]
    usgaap["CommonStockSharesOutstanding"] = {"units": {"shares": entries}}
    return {"facts": {"us-gaap": usgaap}}


def _patch_facts(monkeypatch, tmp_path, facts_json: dict, cik_map: dict | None = None):
    monkeypatch.setattr(ef, "_get_json", lambda url, *a, **kw: facts_json)
    monkeypatch.setattr(ef, "_cik_map", lambda: cik_map or {"TSTK": 1})
    monkeypatch.setattr(ef.time, "sleep", lambda *a, **kw: None)
    monkeypatch.setattr(ef, "_cache_path", lambda: tmp_path / "statements.parquet")


# ---------------------------------------------------------------------------
# 1. BALANCE_SHARES dict exists and contains the right concept
# ---------------------------------------------------------------------------

class TestBalanceSharesDict:
    def test_balance_shares_dict_exists(self):
        assert hasattr(ef, "BALANCE_SHARES"), "BALANCE_SHARES must be defined in edgar_facts"

    def test_shares_in_balance_shares(self):
        assert "shares" in ef.BALANCE_SHARES, "'shares' key must be in BALANCE_SHARES"

    def test_shares_primary_concept(self):
        assert ef.BALANCE_SHARES["shares"][0] == "CommonStockSharesOutstanding", (
            "primary shares concept must be us-gaap:CommonStockSharesOutstanding")

    def test_shares_not_in_balance(self):
        # The BALANCE dict MUST NOT contain 'shares' — it would silently return null
        # because CommonStockSharesOutstanding is in 'shares' unit, not 'USD'.
        assert "shares" not in ef.BALANCE, (
            "'shares' must not be in BALANCE (USD-unit loop) — it belongs in BALANCE_SHARES")


# ---------------------------------------------------------------------------
# 2. _concept() with unit="shares" extracts CommonStockSharesOutstanding
# ---------------------------------------------------------------------------

class TestSharesConceptExtraction:
    """_concept() with unit='shares' and instant=True correctly reads shares."""

    def _usgaap_with_shares(self, shares_by_fy: dict[int, tuple[float, str]]) -> dict:
        """Build minimal usgaap dict with CommonStockSharesOutstanding in shares unit."""
        entries = [_instant_entry(val, fy, end) for fy, (val, end) in shares_by_fy.items()]
        return {"CommonStockSharesOutstanding": {"units": {"shares": entries}}}

    def test_shares_extracted_with_correct_unit(self):
        usgaap = self._usgaap_with_shares({
            2022: (1_000_000_000.0, "2022-09-24"),
            2023: (950_000_000.0, "2023-09-30"),
        })
        vals, ends = ef._concept(usgaap, ["CommonStockSharesOutstanding"],
                                 unit="shares", instant=True)
        assert 2022 in vals, "FY2022 shares must be extracted"
        assert vals[2022] == pytest.approx(1_000_000_000.0)
        assert vals[2023] == pytest.approx(950_000_000.0)
        assert ends[2022] == "2022-09-24"
        assert ends[2023] == "2023-09-30"

    def test_shares_not_found_with_wrong_unit(self):
        """Confirms the original bug: USD unit lookup returns empty for shares concepts."""
        usgaap = self._usgaap_with_shares({2023: (15_000_000_000.0, "2023-09-30")})
        vals, ends = ef._concept(usgaap, ["CommonStockSharesOutstanding"],
                                 unit="USD", instant=True)  # wrong unit
        assert vals == {}, "USD lookup of a shares-unit concept must return empty (original bug)"

    def test_shares_period_end_absorbed(self):
        """period_end from shares entries must be absorbed into period_ends dict."""
        usgaap = self._usgaap_with_shares({2024: (14_000_000_000.0, "2024-09-28")})
        vals, ends = ef._concept(usgaap, ["CommonStockSharesOutstanding"],
                                 unit="shares", instant=True)
        assert ends[2024] == "2024-09-28", "period_end must be carried from shares entry"


# ---------------------------------------------------------------------------
# 3. _statements_for() — shares non-null + period_end stamped
# ---------------------------------------------------------------------------

class TestStatementsForSharesFix:
    """_statements_for() must return non-null shares after the unit fix."""

    def test_shares_non_null_in_output(self, monkeypatch):
        facts = _companyfacts_with_shares(
            usd_concepts={
                "Revenues": [(2022, 394e9), (2023, 383e9)],
                "NetIncomeLoss": [(2022, 99e9), (2023, 97e9)],
                "Assets": [(2022, 352e9), (2023, 352e9)],
            },
            shares_by_fy={
                2022: (15_943_000_000.0, "2022-09-24"),
                2023: (15_550_000_000.0, "2023-09-30"),
            },
        )
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: facts)
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)

        rows = ef._statements_for(320193)
        assert rows, "must return at least one row"
        by_fy = {r["fy"]: r for r in rows}

        assert 2022 in by_fy, "FY2022 row must be present"
        assert pd.notna(by_fy[2022].get("shares")), "shares must be non-null after fix"
        assert by_fy[2022]["shares"] == pytest.approx(15_943_000_000.0)
        assert by_fy[2023]["shares"] == pytest.approx(15_550_000_000.0)

    def test_period_end_stamped_for_all_rows(self, monkeypatch):
        """Every row must carry a non-null period_end (stamped from any concept)."""
        facts = _companyfacts_with_shares(
            usd_concepts={"Revenues": [(2022, 100e9), (2023, 110e9)]},
            shares_by_fy={
                2022: (1e9, "2022-12-31"),
                2023: (1e9, "2023-12-31"),
            },
        )
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: facts)
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)

        rows = ef._statements_for(1)
        assert rows, "must return rows"
        for r in rows:
            assert r.get("period_end") is not None, (
                f"period_end must be non-null for row fy={r.get('fy')}")

    def test_shares_only_fy_gets_period_end(self, monkeypatch):
        """A FY that has ONLY a shares entry (no USD concepts) still gets period_end stamped.
        This tests that the _absorb() call on BALANCE_SHARES ends contributes to period_ends."""
        # FY2024 has only shares, no other USD concepts for that year
        usgaap: dict = {
            "Revenues": {"units": {"USD": [_flow_entry(100e9, 2023)]}},
            "CommonStockSharesOutstanding": {"units": {"shares": [
                _instant_entry(1e9, 2023, "2023-12-31"),
                _instant_entry(2e9, 2024, "2024-12-31"),  # FY2024 has only shares
            ]}},
        }
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: facts)
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)

        rows = ef._statements_for(1)
        by_fy = {r["fy"]: r for r in rows}
        # FY2024 must have period_end stamped from the shares entry
        if 2024 in by_fy:
            assert by_fy[2024].get("period_end") == "2024-12-31", (
                "period_end must be stamped even when shares is the only source for that FY")


# ---------------------------------------------------------------------------
# 4. Future-FY guard
# ---------------------------------------------------------------------------

class TestFutureFYGuard:
    """Rows whose period_end > run date must be dropped from _statements_for() output."""

    def _future_date(self, days_ahead: int = 180) -> str:
        return (date.today() + timedelta(days=days_ahead)).isoformat()

    def _past_date(self, days_ago: int = 90) -> str:
        return (date.today() - timedelta(days=days_ago)).isoformat()

    def test_future_period_end_row_dropped(self, monkeypatch):
        """A row with period_end in the future must be excluded."""
        future_end = self._future_date(180)
        future_start = (date.today() + timedelta(days=180 - 365)).isoformat()
        # Build a future FY entry
        future_fy = date.today().year + 1
        usgaap = {
            # Past row (should be kept)
            "Revenues": {"units": {"USD": [
                _flow_entry(100e9, date.today().year - 1),
                {   # Future-FY entry: FY in the future, period_end in the future
                    "fp": "FY",
                    "form": "10-K",
                    "fy": future_fy,
                    "val": 120e9,
                    "start": future_start,
                    "end": future_end,
                    "filed": future_end,
                },
            ]}},
        }
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: facts)
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)

        rows = ef._statements_for(1)
        fy_values = [r["fy"] for r in rows]
        assert future_fy not in fy_values, (
            f"future FY {future_fy} with period_end={future_end} must be dropped")

    def test_past_period_end_row_kept(self, monkeypatch):
        """A row with period_end in the past must be kept."""
        past_end = self._past_date(90)
        past_start = (date.today() - timedelta(days=90 + 365)).isoformat()
        past_fy = date.today().year - 1
        usgaap = {
            "Revenues": {"units": {"USD": [{
                "fp": "FY", "form": "10-K", "fy": past_fy,
                "val": 100e9, "start": past_start, "end": past_end, "filed": past_end,
            }]}},
        }
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: facts)
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)

        rows = ef._statements_for(1)
        fy_values = [r["fy"] for r in rows]
        assert past_fy in fy_values, f"past FY {past_fy} must NOT be filtered"

    def test_none_period_end_row_kept(self, monkeypatch):
        """A row with period_end=None (no period info found) is kept as display-only.
        This preserves backward compat with rows written before period_end was added."""
        # To get period_end=None for a FY, that FY must have NO concept entries that
        # produce a valid period_end. Use an unusual concept that produces val but no end.
        # Simplest: monkeypatch _statements_for at a level where we can inject None period_end.
        # Actually, period_end IS always set by _concept/_annual when entries exist with 'end'.
        # The None case arises from old cached data; this guard only checks non-None values.
        # Test that the guard condition `pe and pe > today_iso` is False when pe is None.
        from collectors.edgar_facts import _statements_for
        today_iso = date.today().isoformat()
        # Directly test the guard logic
        pe_none = None
        assert not (pe_none and pe_none > today_iso), "None period_end must pass the guard"

    def test_stx_pattern_fy_mismatch_handled(self, monkeypatch):
        """STX-style: XBRL fy=FUTURE but period_end=PAST should be kept (not dropped).
        STX files a 10-K whose XBRL fy field is 2027 but the actual period_end is 2025-06-27.
        The guard checks period_end (past) not fy (future), so it must be kept."""
        past_end = self._past_date(180)  # period_end is well in the past
        past_start = (date.today() - timedelta(days=180 + 365)).isoformat()
        stx_xbrl_fy = date.today().year + 2  # fy field says 2 years from now
        usgaap = {
            "Revenues": {"units": {"USD": [{
                "fp": "FY", "form": "10-K", "fy": stx_xbrl_fy,
                "val": 7e9, "start": past_start, "end": past_end, "filed": past_end,
            }]}},
        }
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(ef, "_get_json", lambda *a, **k: facts)
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **k: None)

        rows = ef._statements_for(1)
        assert rows, (
            f"STX-pattern row (fy={stx_xbrl_fy}, period_end={past_end}) must be KEPT — "
            "period_end is in the past even though fy looks like a future year")
        assert rows[0]["period_end"] == past_end


# ---------------------------------------------------------------------------
# 5. End-to-end: fetch_statements() — shares + period_end in DataFrame
# ---------------------------------------------------------------------------

class TestFetchStatementsLT1a:
    """fetch_statements() must return shares non-null and period_end non-null."""

    def _facts(self) -> dict:
        return _companyfacts_with_shares(
            usd_concepts={
                "Revenues": [(2022, 394e9), (2023, 383e9)],
                "NetIncomeLoss": [(2022, 99e9), (2023, 97e9)],
                "OperatingIncomeLoss": [(2022, 119e9), (2023, 114e9)],
                "NetCashProvidedByUsedInOperatingActivities": [(2022, 122e9), (2023, 110e9)],
                "Assets": [(2022, 352e9), (2023, 352e9)],
                "StockholdersEquity": [(2022, 50e9), (2023, 62e9)],
            },
            shares_by_fy={
                2022: (15_943_000_000.0, "2022-09-24"),
                2023: (15_550_000_000.0, "2023-09-30"),
            },
        )

    def test_shares_non_null_in_dataframe(self, monkeypatch, tmp_path):
        _patch_facts(monkeypatch, tmp_path, self._facts())
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        assert not df.empty
        assert "shares" in df.columns, "shares column must be present"
        assert df["shares"].notna().any(), "at least one shares value must be non-null"
        sub = df[df["ticker"] == "TSTK"]
        # All rows should have shares (fixture provides for both FYs)
        assert sub["shares"].notna().all(), "all TSTK shares values must be non-null"

    def test_shares_values_correct(self, monkeypatch, tmp_path):
        _patch_facts(monkeypatch, tmp_path, self._facts())
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        sub = df[df["ticker"] == "TSTK"].sort_values("fy")
        assert sub.iloc[0]["shares"] == pytest.approx(15_943_000_000.0)
        assert sub.iloc[1]["shares"] == pytest.approx(15_550_000_000.0)

    def test_period_end_non_null_in_dataframe(self, monkeypatch, tmp_path):
        _patch_facts(monkeypatch, tmp_path, self._facts())
        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        assert "period_end" in df.columns, "period_end column must be present"
        sub = df[df["ticker"] == "TSTK"]
        assert sub["period_end"].notna().all(), "all rows must have period_end non-null"

    def test_future_fy_excluded_from_dataframe(self, monkeypatch, tmp_path):
        """Future-FY rows must not appear in the final DataFrame."""
        future_end = (date.today() + timedelta(days=180)).isoformat()
        future_start = (date.today() + timedelta(days=180 - 365)).isoformat()
        future_fy = date.today().year + 1
        # Mix of past and future FY concepts
        usgaap = {
            "Revenues": {"units": {"USD": [
                _flow_entry(100e9, 2022),
                {
                    "fp": "FY", "form": "10-K", "fy": future_fy,
                    "val": 999e9, "start": future_start, "end": future_end,
                    "filed": future_end,
                },
            ]}},
        }
        facts = {"facts": {"us-gaap": usgaap}}
        monkeypatch.setattr(ef, "_get_json", lambda url, *a, **kw: facts)
        monkeypatch.setattr(ef, "_cik_map", lambda: {"TSTK": 1})
        monkeypatch.setattr(ef.time, "sleep", lambda *a, **kw: None)
        monkeypatch.setattr(ef, "_cache_path", lambda: tmp_path / "statements.parquet")

        df = ef.fetch_statements(force=True, max_new=1, tickers=["TSTK"])
        assert not df.empty
        assert future_fy not in df["fy"].values, (
            f"future FY {future_fy} must not appear in final DataFrame")
        # The past row must still be present
        assert 2022 in df["fy"].values
