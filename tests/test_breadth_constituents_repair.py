"""Constituents repair guard for the breadth collectors (BreadthAdapter._repair).

Wikipedia's index-membership tables are community-edited and periodically ship a
plausible-but-wrong symbol — vandalism (Marsh & McLennan as the non-existent
"MRSH") or a stale pre-rename ticker (Fiserv as "FISV", now "FI") — plus the odd
non-ticker junk cell. Unrepaired, those silently drop the real name from the
searchable universe. These are pure-function tests (no network): they build a
synthetic scrape and assert the repair normalises, de-junks, fixes, and dedups.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import BreadthAdapter  # noqa: E402


def _adapter(fixups: dict) -> BreadthAdapter:
    # skip __init__/config.load — _repair only reads self.cfg + self.name
    a = BreadthAdapter.__new__(BreadthAdapter)
    a.cfg = {"ticker_fixups": fixups}
    return a


def test_repair_fixes_vandalism_stale_and_drops_junk():
    a = _adapter({"MRSH": "MMC", "FISV": "FI"})
    df = pd.DataFrame({
        "symbol": ["AAPL", "BRK.B", "MRSH", "FISV", "—", "n/a", "MMC"],
        "name": ["Apple", "Berkshire", "Marsh McLennan", "Fiserv",
                 "junk", "junk", "Marsh dup"],
        "sector": ["IT", "Fin", "Fin", "Fin", "x", "x", "Fin"],
    })
    out = a._repair(df)
    syms = list(out["symbol"])
    # vandalism + stale renames repaired to the real current ticker
    assert "MMC" in syms and "FI" in syms
    assert "MRSH" not in syms and "FISV" not in syms
    # BRK.B normalised to the yfinance form
    assert "BRK-B" in syms
    # non-ticker junk dropped
    assert "—" not in syms and "N/A" not in syms
    # the repaired MRSH row collides with the genuine MMC row -> kept once
    assert syms.count("MMC") == 1
    # output keeps the reference columns and a clean index
    assert list(out.columns) == ["symbol", "name", "sector"]


def test_repair_is_noop_without_fixups():
    a = _adapter({})
    df = pd.DataFrame({"symbol": ["AAPL", "MSFT", "BRK.B"],
                       "name": ["a", "b", "c"], "sector": ["IT", "IT", "Fin"]})
    out = a._repair(df)
    assert list(out["symbol"]) == ["AAPL", "MSFT", "BRK-B"]


def test_repair_handles_lowercase_and_whitespace_symbols():
    a = _adapter({"FISV": "FI"})
    df = pd.DataFrame({"symbol": [" aapl ", "fisv"],
                       "name": ["Apple", "Fiserv"], "sector": ["IT", "Fin"]})
    out = a._repair(df)
    assert set(out["symbol"]) == {"AAPL", "FI"}


# --- issuer-name transport residue -------------------------------------------
# Wikipedia's tables are wiki MARKUP, where "|" separates cells. One leaked into
# the S&P 500 table and made RMD's issuer "ResMed|", which then reached the
# <title>, meta description, OpenGraph, JSON-LD Corporation.name and the visible
# company name of the public dossier. `symbol` had three layers of cleanup here;
# `name` had none.

def test_sanitize_company_name_strips_delimiter_residue():
    s = BreadthAdapter.sanitize_company_name
    assert s("ResMed|") == "ResMed"              # the measured defect (RMD)
    assert s("|Leading") == "Leading"
    assert s("Foo|Bar") == "Foo"                 # a leaked neighbouring cell
    assert s("Acme;;") == "Acme"
    assert s("Acme,") == "Acme"
    assert s("  Spaced   Out  ") == "Spaced Out"
    assert s("") == "" and s(None) == ""


def test_sanitize_company_name_preserves_legitimate_punctuation():
    """Punctuation inside a company name is load-bearing — an over-eager cleanup
    would corrupt far more issuers than the delimiter leak it set out to fix."""
    s = BreadthAdapter.sanitize_company_name
    for name in ("AT&T Inc.", "Johnson & Johnson", "O'Reilly Automotive, Inc.",
                 "Berkshire Hathaway Inc.", "Alphabet Inc. (Class A)",
                 "Coca-Cola", "Smith A.O. Corp.", "Mastercard Inc.",
                 "Moody's", "Lowe's Companies, Inc.", "3M", "E.W. Scripps"):
        assert s(name) == name, f"sanitiser must not alter {name!r}"


def test_repair_sanitises_issuer_names_end_to_end():
    a = _adapter({})
    df = pd.DataFrame({
        "symbol": ["RMD", "T", "JNJ"],
        "name": ["ResMed|", "AT&T Inc.", "Johnson & Johnson"],
        "sector": ["Health Care", "Comm", "Health Care"],
    })
    out = a._repair(df).set_index("symbol")
    assert out.loc["RMD", "name"] == "ResMed"
    # ... and the neighbouring rows are untouched
    assert out.loc["T", "name"] == "AT&T Inc."
    assert out.loc["JNJ", "name"] == "Johnson & Johnson"
