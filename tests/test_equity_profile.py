"""Tests for collectors/equity_profile.py — the Wikipedia/SEC business-profile
collector. Focused on the *offline* resolution logic that decides which page a
ticker maps to (no network): name cleaning, search-term generation, and the
two-gate validator (name-relevance AND organization-type) that keeps a lawsuit /
town / chemical / person page out of the "Business profile" blurb.

pytest is not installed in the venv — run as a plain script:
    python tests/test_equity_profile.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import equity_profile as EP  # noqa: E402


def test_clean_name():
    assert EP._clean_name("MICROSOFT CORP") == "Microsoft Corp"        # de-shout
    assert EP._clean_name("Hershey Company (The)") == "The Hershey Company"
    assert EP._clean_name("Walt Disney Company (The)") == "The Walt Disney Company"
    assert EP._clean_name("ENTERGY CORP /DE/") == "Entergy Corp"        # reg tag
    assert EP._clean_name("KEYCORP /NEW/") == "Keycorp"
    assert EP._clean_name("AMETEK INC/") == "Ametek Inc"               # stray slash
    assert EP._clean_name("Apple Inc.") == "Apple Inc."               # already clean
    assert EP._clean_name("3M") == "3M"                               # short, untouched


def test_core_name():
    assert EP._core_name("Microsoft Corp") == "Microsoft"
    assert EP._core_name("CVR Energy, Inc.") == "CVR Energy"
    assert EP._core_name("MICROSOFT CORP") == "Microsoft"
    assert EP._core_name("Argan, Inc.") == "Argan"


def test_search_terms_prefers_clean_display_name():
    # clean breadth name first, SEC ALL-CAPS name as backup; deduped
    terms = EP._search_terms("Microsoft", "MICROSOFT CORP")
    assert terms[0] == "Microsoft"
    assert "Microsoft Corp" in terms
    # no bare brand token (those surface a same-named different entity)
    assert "EPAM" not in EP._search_terms("EPAM Systems, Inc.", "EPAM SYSTEMS INC")


def test_lawsuit_title():
    assert EP._lawsuit_title("Microsoft Corp. v European Commission")
    assert EP._lawsuit_title("Altria Group v. Good")
    assert not EP._lawsuit_title("Visa Inc.")
    assert not EP._lawsuit_title("Vontier Corporation")


def test_name_relevance_rejects_fuzzy_namesakes():
    # the company
    assert EP._name_relevant("Microsoft", "Microsoft", "MICROSOFT CORP")
    # a lawsuit page still names the company (org-gate, not this, rejects it)
    assert EP._name_relevant("Microsoft Corp. v European Commission", "Microsoft")
    # fuzzy opensearch garbage shares no real token
    assert not EP._name_relevant("Arginine", "Argan, Inc.")
    assert not EP._name_relevant("Sugar Land, Texas", "CVR Energy, Inc.")
    assert not EP._name_relevant("Corfu incident", "Cohu, Inc.")
    # a generic industry word must NOT anchor a match
    assert not EP._name_relevant("Cove Energy plc", "CVR Energy, Inc.")


def test_name_relevance_fused_token():
    # a distinctive token fused into the page title ("Eagle" -> "EagleBank")
    assert EP._name_relevant("EagleBank", "Eagle Bancorp, Inc.", "EAGLE BANCORP INC")
    assert EP._name_relevant("ExxonMobil", "Exxon Mobil Corporation")


def test_match_score_prefers_full_name():
    # full core match
    assert EP._match_score("Microsoft", "Microsoft", "MICROSOFT CORP") == 3
    assert EP._match_score("ACM Research", "ACM Research, Inc.") == 3
    # all distinctive tokens present (incl. fused) but not the exact core
    assert EP._match_score("EagleBank", "Eagle Bancorp, Inc.") >= 2
    assert EP._match_score("AST Research", "ACM Research, Inc.") == 2  # shares "research"
    # only SOME of a multi-word distinctive name -> the wrong-sibling smell
    assert EP._match_score("Antero Resources", "Antero Midstream") == 1
    assert EP._match_score("Apollo Global Management",
                           "Apollo Commercial Real Estate Finance") == 1
    # unrelated
    assert EP._match_score("Arginine", "Argan, Inc.") == 0
    # _name_relevant is the score>=1 view
    assert EP._name_relevant("Antero Resources", "Antero Midstream")
    assert not EP._name_relevant("Arginine", "Argan, Inc.")


def test_looks_company_keyword_gate():
    assert EP._looks_company("American multinational technology company", "")
    assert EP._looks_company("Real estate investment trust", "")
    assert EP._looks_company("American insurance brokerage", "")
    # no organization word -> not a company
    assert not EP._looks_company("Legal case", "")
    assert not EP._looks_company("Amino acid", "")


def test_looks_company_veto_overrides_keyword():
    # "unincorporated community" contains "incorporat" — the veto must win
    assert not EP._looks_company("Unincorporated community in Minnesota, United States", "")
    # a place / work / case never reads as a company
    assert not EP._looks_company("City in the United States", "")
    assert not EP._looks_company("2008 United States Supreme Court case", "")
    assert not EP._looks_company("Country club in Hershey, Pennsylvania", "")
    # a same-named PERSON (jewellery designer) is not the company
    assert not EP._looks_company("French jewellery designer", "")
    assert not EP._looks_company(
        "", "Jean Michel Schlumberger was a major French jewellery designer")


def test_looks_company_designer_company_still_passes():
    # a real company whose blurb says "designer" must still pass via other words
    assert EP._looks_company(
        "", "Broadcom Inc. is an American multinational designer, developer, "
            "and manufacturer of semiconductor products")
    assert EP._looks_company("American semiconductor company", "")


def test_is_company_page_end_to_end():
    msft = {"type": "standard", "title": "Microsoft",
            "description": "American multinational technology company",
            "extract": "Microsoft Corporation is an American multinational "
                       "technology company headquartered in Redmond."}
    assert EP._is_company_page(msft, "Microsoft", "MICROSOFT CORP")

    lawsuit = {"type": "standard", "title": "Microsoft Corp. v European Commission",
               "description": "Legal case",
               "extract": "Microsoft Corp. v Commission ... is a case brought by ..."}
    assert not EP._is_company_page(lawsuit, "Microsoft", "MICROSOFT CORP")

    town = {"type": "standard", "title": "Knife River, Minnesota",
            "description": "Unincorporated community in Minnesota, United States",
            "extract": "Knife River is an unincorporated community in Lake County."}
    assert not EP._is_company_page(town, "Knife River Corporation", "KNIFE RIVER CORP")

    disambig = {"type": "disambiguation", "title": "AZZ",
                "description": "Topics referred to by the same term", "extract": ""}
    assert not EP._is_company_page(disambig, "AZZ, Inc.")


def test_trim_protects_single_letter_initials():
    # without the fix this collapses to "W. W." / "W. P."
    assert EP._trim("W. W. Grainger, Inc. is an American industrial supply company."
                    " It was founded in 1927.") == \
        "W. W. Grainger, Inc. is an American industrial supply company."
    assert EP._trim("W. P. Carey Inc. is a real estate investment trust that invests"
                    " in commercial properties. Based in New York.").startswith(
        "W. P. Carey Inc. is a real estate investment trust")
    # ordinary blurbs are unchanged (no churn)
    assert EP._trim("Apple Inc. is an American multinational technology company "
                    "headquartered in Cupertino, California. It is known for "
                    "consumer electronics.") == \
        "Apple Inc. is an American multinational technology company headquartered " \
        "in Cupertino, California."


def test_trim_empty():
    assert EP._trim("") == ""
    assert EP._trim(None) == ""


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(_run())
