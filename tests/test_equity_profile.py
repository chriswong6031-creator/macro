"""Tests for collectors/equity_profile.py — the Wikipedia/SEC business-profile
collector. Focused on the *offline* resolution logic that decides which page a
ticker maps to (no network): name cleaning, search-term generation, and the
two-gate validator (name-relevance AND organization-type) that keeps a lawsuit /
town / chemical / person page out of the "Business profile" blurb.

pytest is not installed in the venv — run as a plain script:
    python tests/test_equity_profile.py
"""
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

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


def test_cell_coerces_missing_to_none():
    # round-tripped parquet object columns come back as float NaN, which is truthy
    # as a string ("nan") — _cell must normalise it to None
    assert EP._cell(float("nan")) is None
    assert EP._cell(None) is None
    assert EP._cell("Apple Inc.") == "Apple Inc."
    assert EP._cell(3) == 3


def test_int0_safe_counts():
    assert EP._int0(float("nan")) == 0
    assert EP._int0(None) == 0
    assert EP._int0(2.0) == 2          # parquet stores int cols as float
    assert EP._int0("3") == 3
    assert EP._int0("garbage") == 0


def _fetch_with_stubs(existing: pd.DataFrame, wiki):
    """Run fetch_profiles against a temp cache with the network stubbed out: SEC
    skipped (empty cik map), universe = the cache's own rows, Wikipedia = `wiki`."""
    saved = (EP._cache_path, EP._cik_map, EP._universe, EP._wiki_description, EP._sec_submission)
    with tempfile.TemporaryDirectory() as d:
        cache = Path(d) / "profiles.parquet"
        existing.to_parquet(cache)
        EP._cache_path = lambda: cache
        EP._cik_map = lambda: {}                                  # SEC skipped entirely
        EP._universe = lambda: {t: f"{t} Inc" for t in existing.index}
        EP._wiki_description = wiki
        EP._sec_submission = lambda cik: {}
        try:
            return EP.fetch_profiles()
        finally:
            (EP._cache_path, EP._cik_map, EP._universe,
             EP._wiki_description, EP._sec_submission) = saved


def test_fetch_retries_only_eligible_description_gaps():
    """The core fix: a description-less row is retried on the short DESC_RETRY_DAYS
    cadence (bounded by MAX_DESC_TRIES) instead of being frozen for REFRESH_DAYS —
    while good/too-recent/exhausted rows are left untouched, and prior identity +
    a previously-good blurb are never regressed by a failed retry."""
    def iso(days):
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    existing = pd.DataFrame(
        {
            # ticker:        description,    as_of,        desc_tries, sic_description
            "GOOD":         ["Good co desc", iso(1),       float("nan"), "Apples"],
            "RETRY_OK":     [None,           iso(5),       2.0,          "Widgets"],
            "RETRY_FAIL":   [None,           iso(5),       2.0,          "Gadgets"],
            "TOO_SOON":     [None,           iso(1),       1.0,          "Sprockets"],
            "EXHAUSTED":    [None,           iso(10),      float(EP.MAX_DESC_TRIES), "Cogs"],
            "STALE_REGRESS":["Keep me",      iso(200),     float("nan"), "Bolts"],
        },
        index=["description", "as_of", "desc_tries", "sic_description"],
    ).T
    existing.index.name = "ticker"

    # Wikipedia succeeds for everyone EXCEPT names carrying FAIL/REGRESS in them
    # Returns (extract, title): title is reused by the offshore-attention collector.
    def wiki(*names):
        nm = " ".join(str(n) for n in names if n)
        if "FAIL" in nm or "REGRESS" in nm:
            return None, None
        return f"{names[0]} is a company.", str(names[0]).replace(" ", "_")

    out = _fetch_with_stubs(existing, wiki)

    # eligible gap retried and filled; counter reset; identity preserved
    assert isinstance(out.loc["RETRY_OK", "description"], str) and out.loc["RETRY_OK", "description"]
    assert EP._int0(out.loc["RETRY_OK", "desc_tries"]) == 0
    assert out.loc["RETRY_OK", "sic_description"] == "Widgets"

    # eligible gap retried, still empty → counter increments, identity preserved
    assert EP._cell(out.loc["RETRY_FAIL", "description"]) is None
    assert EP._int0(out.loc["RETRY_FAIL", "desc_tries"]) == 3
    assert out.loc["RETRY_FAIL", "sic_description"] == "Gadgets"

    # too-recent and try-exhausted gaps are left alone (still empty, counter unchanged)
    assert EP._cell(out.loc["TOO_SOON", "description"]) is None
    assert EP._int0(out.loc["TOO_SOON", "desc_tries"]) == 1
    assert EP._int0(out.loc["EXHAUSTED", "desc_tries"]) == EP.MAX_DESC_TRIES

    # a good blurb is untouched; a stale refresh that fails must NOT erase it
    assert out.loc["GOOD", "description"] == "Good co desc"
    assert out.loc["STALE_REGRESS", "description"] == "Keep me"


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
