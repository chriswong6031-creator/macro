"""Company-name -> ticker resolver (engine/name_resolver.py).

Pins name normalization, the leading-company-span extraction, and the conservative
exact-unique + market-scoped resolution (ambiguous / generic / cross-market -> None),
plus a real-data smoke against the on-disk digest_db index.
"""
from __future__ import annotations

from engine import name_resolver as nr


def test_normalize_name_strips_legal_forms():
    assert nr.normalize_name("Acme Corporation, Inc.") == "acme"
    assert nr.normalize_name("ARC Resources Ltd.") == "arc resources"
    assert nr.normalize_name("Barclays PLC") == "barclays"
    assert nr.normalize_name("Cosan S.A.") == "cosan"
    assert nr.normalize_name("") == ""


def test_lead_company_extracts_span():
    assert nr.lead_company("Acme Corp announces strategic review") == "Acme Corp"
    assert nr.lead_company("Barclays plc (LSE: BARC) Rule 2.7 offer") == "Barclays plc"
    assert nr.lead_company("ARC Resources Ltd to be acquired by Foo") == "ARC Resources Ltd"


def test_resolve_exact_unique_and_market_scope():
    idx = {"acme": {"ACME"}, "barclays": {"BARC.L"}, "arc resources": {"ARX.TO"},
           "ambig co": {"AMB1", "AMB2"}, "dual": {"DUAL", "DUAL.L"}}
    assert nr.resolve("Acme Corporation announces strategic review", index=idx) == "ACME"
    assert nr.resolve("Barclays plc firm offer", market="uk", index=idx) == "BARC.L"
    assert nr.resolve("ARC Resources Ltd to be acquired", market="canada", index=idx) == "ARX.TO"
    # ambiguous normalized name -> None
    assert nr.resolve("Ambig Co announces", index=idx) is None
    # cross-market filter: ACME is US, asked for UK -> None
    assert nr.resolve("Acme announces", market="uk", index=idx) is None
    # market scoping disambiguates a dual listing
    assert nr.resolve("Dual Inc offer", market="uk", index=idx) == "DUAL.L"
    assert nr.resolve("Dual Inc offer", market="us", index=idx) == "DUAL"
    # unknown / too-generic -> None
    assert nr.resolve("Unknown Co announces", index=idx) is None
    assert nr.resolve("US announces", index=idx) is None


def test_resolve_real_digest_index():
    nr.clear_cache()
    idx = nr.build_index()
    if not idx:
        return  # no digest_db on disk in this env -> skip the smoke
    # names known to be in the digest universe (US bare ticker; CA suffixed)
    assert nr.resolve("Bally's Corporation explores alternatives", market="us", index=idx) == "BALY"
    assert nr.resolve("ARC Resources Ltd announces a deal", market="canada", index=idx) == "ARX.TO"
