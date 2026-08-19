"""Regression coverage for the NA-ticker pandas-sentinel defect (PR #5936 sibling).

pandas decodes the strings NA/NULL/NONE/NAN/N-A/NaN into NaN by default. Real
listings carry 'NA' as a ticker — Nano Labs Ltd on Nasdaq AND National Bank of
Canada on the TSX — so every collectors/ parse site that reads a ticker/symbol
column must pass keep_default_na=False, na_values=[""] to read_csv/read_excel
(bare keep_default_na=False alone is a REGRESSION: it also stringifies every
numeric column, since blank cells no longer decode to NaN either — verified on
pandas 3.0.5 in this tree, see test_bare_keep_default_na_is_a_regression below).

Three layers are covered:
  1. A static AST guard over the 9 owned collector files, pinning both the total
     read_csv/read_excel call count and the guarded-call count per file, so a
     newly-added unguarded parse site fails the test.
  2. Behavioural round-trips proving the motivating exemplar (NA / Nano Labs /
     National Bank of Canada) survives parsing with the real kwargs.
  3. The is_non_equity_holding() truth table for the downstream sentinel fix in
     collectors/holdings.py (_AMBIGUOUS_SENTINEL_TICKERS).
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent

# (relpath, total read_csv/read_excel calls in file, calls carrying BOTH
# keep_default_na and na_values). The gap between total and guarded is the
# known LOW-SKIP read_excel(header=None) raw dumps in etf_holdings.py (recon'd
# out of the frozen 15-site list — see the MISSION packet).
_SITES = [
    ("collectors/etf_holdings.py", 9, 6),
    ("collectors/holdings.py", 2, 2),
    ("collectors/canada_universe.py", 1, 1),
    ("collectors/intl_universe.py", 1, 1),
    ("collectors/massive_flatfiles.py", 1, 1),
    ("collectors/sec_insider.py", 1, 1),
    ("collectors/hk_shorts.py", 1, 1),
    ("collectors/thetadata.py", 1, 1),
    ("collectors/sector_holdings.py", 1, 1),
]


def _parse_calls(path: Path) -> list[set[str]]:
    """Keyword-arg name sets for every read_csv/read_excel Call node in `path`.
    Pure source parse via ast — does NOT import the module (no network deps)."""
    tree = ast.parse(path.read_text())
    calls: list[set[str]] = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("read_csv", "read_excel")):
            calls.append({kw.arg for kw in node.keywords if kw.arg})
    return calls


@pytest.mark.parametrize("relpath,total,guarded", _SITES)
def test_na_sentinel_guard_present(relpath: str, total: int, guarded: int) -> None:
    calls = _parse_calls(ROOT / relpath)
    assert len(calls) == total, (
        f"{relpath}: expected {total} read_csv/read_excel call(s), found "
        f"{len(calls)} — a new/removed parse site changed the pinned count")
    n_guarded = sum(1 for kw in calls if "keep_default_na" in kw and "na_values" in kw)
    assert n_guarded == guarded, (
        f"{relpath}: expected {guarded} guarded (keep_default_na+na_values) "
        f"parse site(s), found {n_guarded} — a site lost its guard or a "
        f"newly-added site shipped unguarded")


def test_bare_keep_default_na_is_a_regression() -> None:
    """Pins the exact regression the FROZEN SPEC calls out: keep_default_na=False
    alone stops blank cells decoding to NaN, so a numeric column with any blank
    cell silently becomes dtype str/object — breaking every downstream
    pd.to_numeric(errors='coerce') / .dropna(subset=[...]) that assumed a float
    column. na_values=[""] is what keeps the existing behaviour intact."""
    csv_text = "ticker,Weight\nNA,4.2\nRY,10.1\nBNS,\n"       # BNS: blank weight
    default = pd.read_csv(io.StringIO(csv_text))
    bare = pd.read_csv(io.StringIO(csv_text), keep_default_na=False)
    fixed = pd.read_csv(io.StringIO(csv_text), keep_default_na=False, na_values=[""])

    assert pd.isna(default["ticker"].iloc[0])             # {} : NA ticker LOST
    assert default["Weight"].dtype == "float64"

    assert bare["ticker"].tolist() == ["NA", "RY", "BNS"]  # ticker kept ...
    assert bare["Weight"].dtype != "float64"                # ... but Weight broke

    assert fixed["ticker"].tolist() == ["NA", "RY", "BNS"]  # ticker kept
    assert fixed["Weight"].dtype == "float64"                # AND Weight intact
    assert pd.isna(fixed["Weight"].iloc[2])                  # blank cell still -> NaN


# --- behavioural round-trips: the motivating exemplar survives ------------------

def test_to_ticker_na_maps_to_na_dot_to() -> None:
    """collectors.canada_universe._to_ticker('NA') -> 'NA.TO'. Already true today
    (the skip-list is ('CAD','--','-','USD','NAN','NONE') — 'NA' was never in
    it), pinned here so a future skip-list edit cannot silently regress it."""
    from collectors.canada_universe import _to_ticker
    assert _to_ticker("NA") == "NA.TO"
    assert _to_ticker("RY") == "RY.TO"
    assert _to_ticker("NAN") is None    # str(float('nan')) residue — stays dropped
    assert _to_ticker("NONE") is None   # str(None) residue — stays dropped


def test_ishares_xic_na_ticker_survives_and_weight_stays_numeric() -> None:
    """Synthetic iShares XIC-shaped CSV parsed with the exact call
    collectors/canada_universe.py._ishares_holdings now makes: the NA row (
    National Bank of Canada) keeps ticker 'NA' (not NaN) AND the weight column
    stays numeric — the numeric half is what a bare keep_default_na=False would
    have broken."""
    csv_text = (
        "Ticker,Name,Sector,Asset Class,Weight (%)\n"
        "NA,NATIONAL BANK OF CANADA,Financials,Equity,4.2\n"
        "RY,ROYAL BANK OF CANADA,Financials,Equity,10.1\n"
        "BNS,BANK OF NOVA SCOTIA,Financials,Equity,8.3\n"
    )
    df = pd.read_csv(io.StringIO(csv_text), thousands=",",
                     keep_default_na=False, na_values=[""])
    tcol = next(c for c in df.columns if "ticker" in c.lower())
    wcol = next(c for c in df.columns if "weight" in c.lower())

    assert "NA" in df[tcol].tolist()
    na_row = df[df[tcol] == "NA"].iloc[0]
    assert not pd.isna(na_row[tcol])
    assert na_row["Name"] == "NATIONAL BANK OF CANADA"

    w = pd.to_numeric(df[wcol], errors="coerce")
    assert w.notna().all()                       # no numeric row was coerced to NaN
    assert w.iloc[0] == 4.2


def test_etf_normalize_retains_na_ticker_nano_labs() -> None:
    """ETFHoldingsAdapter._normalize (staticmethod) on a frame whose ticker is
    'NA' and name is 'Nano Labs Ltd' retains the row — Part A (parse) + Part B
    (is_non_equity_holding no longer treats bare 'NA' as an unconditional
    sentinel) must compose for the exemplar to actually survive end to end."""
    from collectors.etf_holdings import EtfHoldingsAdapter
    df = pd.DataFrame({
        "ticker": ["NA", "AAPL"],
        "name": ["Nano Labs Ltd", "Apple Inc"],
        "weight": ["1.2", "8.0"],
        "shares_held": ["500", "2000"],
    })
    out = EtfHoldingsAdapter._normalize(df, "XYZ", "2026-08-19",
                                        wcol="weight", scol="shares_held")
    assert "NA" in list(out["ticker"])
    row = out[out["ticker"] == "NA"].iloc[0]
    assert row["name"] == "Nano Labs Ltd"
    assert row["shares"] == 500


# --- is_non_equity_holding truth table (Part B) ---------------------------------

@pytest.mark.parametrize("ticker,name,expected", [
    ("NA", "Nano Labs Ltd", False),
    ("NA", "NATIONAL BANK OF CANADA", False),
    ("NA", "", True),
    ("NA", float("nan"), True),
    ("NA", "USD Cash", True),
    ("NAN", "Nano Labs Ltd", True),     # pandas residue — str(float('nan')) == 'nan'
    ("NONE", "None Inc", True),         # pandas residue — str(None) == 'None'
    ("NULL", "Null Co", True),          # unconditional sentinel, unchanged
])
def test_is_non_equity_holding_na_truth_table(ticker, name, expected) -> None:
    from collectors.holdings import is_non_equity_holding
    assert is_non_equity_holding(ticker, name) is expected
