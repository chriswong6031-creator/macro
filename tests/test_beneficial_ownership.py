"""Schedule 13D/13G beneficial-ownership: filer classification, idx/header parse,
and the activist-vs-aggregation regime grading."""
from __future__ import annotations

import pandas as pd

from collectors.beneficial_ownership import filer_from_header, parse_idx
from engine.beneficial_ownership import classify_filer_type, regime_for, regime_map


def test_classify_filer_type_custodian_deny_list():
    assert classify_filer_type("BlackRock, Inc.") == "passive_giant"
    assert classify_filer_type("THE VANGUARD GROUP") == "passive_giant"
    assert classify_filer_type("JPMorgan Chase & Co") == "passive_giant"
    assert classify_filer_type("Lucerne Capital Management LP") == "other"
    assert classify_filer_type(None) == "unknown"


def test_parse_idx_normalizes_schedule_form_names():
    idx = "\n".join([
        "Form Type   Company Name   CIK   Date Filed   File Name",
        "-----------------------------------------------------------",
        "SCHEDULE 13D     Acme Corp                 1234567     20260115    edgar/data/1234567/0001193125-26-000001.txt",
        "SCHEDULE 13G/A   Beta Holdings Inc         7654321     20260116    edgar/data/7654321/0001193125-26-000002.txt",
        "8-K              Ignore Co                 1111111     20260116    edgar/data/1111111/0001193125-26-000003.txt",
    ])
    rows = parse_idx(idx)
    assert len(rows) == 2                                  # 8-K excluded
    assert rows[0]["form_type"] == "SC 13D"               # normalized from SCHEDULE 13D
    assert rows[1]["form_type"] == "SC 13G/A"
    assert rows[0]["cik"] == "1234567"
    assert rows[0]["date_filed"] == "2026-01-15"
    assert rows[0]["accession"] == "0001193125-26-000001"


def test_filer_from_header_reads_filed_by_not_subject():
    hdr = "\n".join([
        "SUBJECT COMPANY:",
        "\t\tCOMPANY CONFORMED NAME:\t\t\tACME CORP",
        "\t\tCENTRAL INDEX KEY:\t\t\t0001234567",
        "FILED BY:",
        "\t\tCOMPANY CONFORMED NAME:\t\t\tACTIVIST CAPITAL LP",
    ])
    assert filer_from_header(hdr) == "ACTIVIST CAPITAL LP"
    assert filer_from_header("no filer block here") is None


def _df(rows):
    return pd.DataFrame(rows)


def test_regime_activist_13d_is_high():
    r = regime_for(_df([{"form_type": "SC 13D", "date_filed": "2026-01-10",
                         "filer": "Lucerne Capital", "filer_type": "other"}]))
    assert r["state"] == "activist" and r["signal"] == "high" and r["n_13d"] == 1


def test_regime_custodian_13g_is_noise():
    r = regime_for(_df([{"form_type": "SC 13G", "date_filed": "2026-01-10",
                         "filer": "BlackRock, Inc.", "filer_type": "passive_giant"}]))
    assert r["state"] == "custodial" and r["signal"] == "noise"


def test_regime_passive_unknown_is_low():
    r = regime_for(_df([{"form_type": "SC 13G/A", "date_filed": "2026-01-10",
                         "filer": "Small Fund LP", "filer_type": "other"}]))
    assert r["state"] == "passive" and r["signal"] == "low"


def test_regime_13g_to_13d_flip_is_high():
    r = regime_for(_df([
        {"form_type": "SC 13G", "date_filed": "2025-06-01", "filer": "Esc LP", "filer_type": "other"},
        {"form_type": "SC 13D", "date_filed": "2026-01-10", "filer": "Esc LP", "filer_type": "other"},
    ]))
    assert r["is_flip"] is True and r["state"] == "flip" and r["signal"] == "high"


def test_regime_no_flip_when_different_filers():
    # a custodian's old 13G + a different activist's 13D is NOT a same-filer flip
    r = regime_for(_df([
        {"form_type": "SC 13G", "date_filed": "2025-06-01", "filer": "BlackRock, Inc.", "filer_type": "passive_giant"},
        {"form_type": "SC 13D", "date_filed": "2026-01-10", "filer": "Esc LP", "filer_type": "other"},
    ]))
    assert r["is_flip"] is False and r["signal"] == "high"   # still activist via the 13D


def test_regime_map_groups_by_ticker_and_drops_non_13dg():
    ev = _df([
        {"ticker": "AAA", "form_type": "SC 13D", "date_filed": "2026-01-10", "filer": "X", "filer_type": "other"},
        {"ticker": "BBB", "form_type": "SC 13G", "date_filed": "2026-01-10", "filer": "FMR LLC", "filer_type": "passive_giant"},
        {"ticker": "CCC", "form_type": "8-K", "date_filed": "2026-01-10", "filer": "Y", "filer_type": "other"},
    ])
    m = regime_map(ev)
    assert set(m) == {"AAA", "BBB"}                       # 8-K dropped
    assert m["AAA"]["signal"] == "high" and m["BBB"]["signal"] == "noise"
