"""Activist filer track-record (engine/activist.py, P3.2).

Pins the cover-page reporting-person extraction, the filer-name normalization, and the
leak-free per-filer forward-return aggregation with its min-sample gate.
"""
from __future__ import annotations

import pandas as pd

from engine import activist as av


# the canonical Schedule 13D cover page, after markup-stripping to one line
_COVER = (
    "SCHEDULE 13D Under the Securities Exchange Act of 1934 GENCO SHIPPING & TRADING LTD "
    "(Name of Issuer) Common Stock (Title of Class) 12345A678 (CUSIP Number) "
    "1 NAME OF REPORTING PERSON Elliott Investment Management L.P. "
    "2 CHECK THE APPROPRIATE BOX IF A MEMBER OF A GROUP (a) (b) "
    "3 SEC USE ONLY 4 SOURCE OF FUNDS WC")


def test_extract_reporting_person():
    assert av.extract_reporting_person(_COVER) == "Elliott Investment Management L.P."
    # variant label with the IRS-id clause before the name
    v = ("NAMES OF REPORTING PERSONS I.R.S. IDENTIFICATION NOS. OF ABOVE PERSONS (ENTITIES ONLY) "
         "Starboard Value LP 2 CHECK THE APPROPRIATE BOX")
    assert av.extract_reporting_person(v) == "Starboard Value LP"
    assert av.extract_reporting_person("no cover page here") is None
    assert av.extract_reporting_person(None) is None


def test_norm_filer_groups_suffix_variants():
    assert av.norm_filer("Elliott Investment Management L.P.") == av.norm_filer("Elliott Investment Management LP")
    assert av.norm_filer("Starboard Value LP") == "STARBOARD VALUE"
    assert av.norm_filer(None) is None


def test_filer_of_prefers_llm():
    assert av.filer_of({"llm_filer": "Elliott", "filer": "x"}) == "Elliott"
    assert av.filer_of({"llm_filer": None, "filer": "Starboard"}) == "Starboard"
    assert av.filer_of({"llm_filer": None, "filer": None}) is None


def test_filer_track_record_gate_and_returns():
    idx = pd.bdate_range("2026-01-01", periods=200)
    closes = pd.DataFrame({"AAA": [10.0 + i * 0.1 for i in range(200)],   # steady uptrend
                           "BBB": [50.0] * 200}, index=idx)
    rows = []
    # ELLIOTT: 5 priced campaigns on AAA (uptrend -> positive fwd) -> tracked
    for d in ("2026-01-05", "2026-01-12", "2026-01-20", "2026-02-02", "2026-02-10"):
        rows.append({"category": "Activist Campaigns", "status": "ok", "ticker": "AAA",
                     "llm_filer": "Elliott Investment Management LP", "filer": None, "date_filed": d})
    # SMALLFRY: 1 campaign -> descriptive (below min_filings)
    rows.append({"category": "Activist Campaigns", "status": "ok", "ticker": "BBB",
                 "llm_filer": "Smallfry Capital", "filer": None, "date_filed": "2026-01-05"})
    df = pd.DataFrame(rows)
    tr = av.filer_track_record(df, closes, horizon=20, min_filings=4)["by_filer"]
    assert tr[av.norm_filer("Elliott Investment Management LP")]["status"] == "tracked"
    assert tr[av.norm_filer("Elliott Investment Management LP")]["med_fwd_pct"] > 0
    assert tr[av.norm_filer("Smallfry Capital")]["status"] == "descriptive"


def test_filer_track_record_empty():
    assert av.filer_track_record(pd.DataFrame(), pd.DataFrame())["by_filer"] == {}
