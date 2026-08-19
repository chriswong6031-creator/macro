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
    # "research" is an industry descriptor, not a brand — it must not anchor a match
    # on its own. It used to, which made the unrelated "AST Research" score 2 for
    # ACM Research; the real page still matches on its full core below.
    assert EP._match_score("AST Research", "ACM Research, Inc.") == 0
    # only SOME of a multi-word distinctive name -> the wrong-sibling smell
    assert EP._match_score("Antero Resources", "Antero Midstream") == 1
    assert EP._match_score("Apollo Global Management",
                           "Apollo Commercial Real Estate Finance") == 1
    # unrelated
    assert EP._match_score("Arginine", "Argan, Inc.") == 0
    # _name_relevant is now the score>=2 view: a score-1 partial is a DIFFERENT
    # company (Antero Resources is not Antero Midstream), and letting it into the
    # candidate pool is how a real company's blurb reaches another's ticker.
    assert not EP._name_relevant("Antero Resources", "Antero Midstream")
    assert not EP._name_relevant("Arginine", "Argan, Inc.")
    assert EP._name_relevant("Microsoft", "Microsoft", "MICROSOFT CORP")


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

    V = float(EP.RESOLVER_VERSION)
    existing = pd.DataFrame(
        {
            # ticker:        description,    as_of,   desc_tries, sic_description, resolver_version
            "GOOD":         ["Good co desc", iso(1),  float("nan"), "Apples",    V],
            "RETRY_OK":     [None,           iso(5),  2.0,          "Widgets",   V],
            "RETRY_FAIL":   [None,           iso(5),  2.0,          "Gadgets",   V],
            "TOO_SOON":     [None,           iso(1),  1.0,          "Sprockets", V],
            "EXHAUSTED":    [None,           iso(10), float(EP.MAX_DESC_TRIES), "Cogs", V],
            "STALE_REGRESS":["Keep me",      iso(200), float("nan"), "Bolts",    V],
        },
        index=["description", "as_of", "desc_tries", "sic_description",
               "desc_resolver_version"],
    ).T
    existing.index.name = "ticker"

    # Wikipedia succeeds for everyone EXCEPT names carrying FAIL/REGRESS in them.
    # Returns (extract, title, strength): title is reused by the offshore-attention
    # collector; strength is the acceptance class recorded for provenance.
    def wiki(*names, sic_description=None, **kw):
        nm = " ".join(str(n) for n in names if n)
        if "FAIL" in nm or "REGRESS" in nm:
            return None, None, None
        return (f"{names[0]} is a company.", str(names[0]).replace(" ", "_"),
                EP.STRENGTH_EXACT)

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


# --- entity-acceptance: the wrong-company class ------------------------------
def _page(title, description="", extract="", type_="standard"):
    return {"type": type_, "title": title, "description": description, "extract": extract}


def test_industry_families_read_both_vocabularies():
    # SEC SIC text and Wikipedia prose, reduced to the same coarse families
    assert "real_estate" in EP._industry_families("Real Estate Investment Trusts")
    assert "food_service" in EP._industry_families("Redwood is a restaurant in Portland")
    assert "finance" in EP._industry_families("State Commercial Banks")
    # no evidence is NOT a contradiction
    assert EP._industry_families("") == frozenset()
    assert EP._industry_agrees(None, "American technology company", "") is None
    assert EP._industry_agrees("Services-Prepackaged Software", "", "") is None
    # word-boundary matched: no substring false positives
    assert "finance" not in EP._industry_families("a riverbank in Ohio")


def test_industry_adjacency_prevents_false_contradiction():
    # SEC's 1970s taxonomy vs modern prose, same issuer — must NOT contradict
    assert EP._industry_agrees("Electronic Computers",
                               "American multinational technology company", "") is True
    assert EP._industry_agrees("Fire, Marine & Casualty Insurance",
                               "American financial services company", "") is True
    # adjacency is one hop only: retail~food_service and food_service~hospitality
    # must never chain real_estate to food_service
    assert EP._industry_agrees("Real Estate Investment Trusts",
                               "Restaurant in Portland, Oregon", "") is False


def test_accept_rejects_the_published_rwt_restaurant():
    """The defect this version exists for: RWT / Redwood Trust Inc was published
    with the blurb of a Portland restaurant, because "Trust" is a stop word and the
    lone surviving token "redwood" is carried by the restaurant's page."""
    restaurant = _page("Redwood (restaurant)", "Restaurant in Portland, Oregon",
                       "Redwood is a restaurant in Portland, Oregon, United States. "
                       "Established in 2013, it operates in the Montavilla neighborhood.")
    ok, strength = EP._accept_page(restaurant, "Real Estate Investment Trusts",
                                   "Redwood Trust Inc", "REDWOOD TRUST INC")
    assert not ok, "a restaurant must never be published as a mortgage REIT"
    assert strength == EP.STRENGTH_WEAK          # one token agreed, and it is a namesake
    # the real issuer page is accepted on its full core name
    real = _page("Redwood Trust", "American real estate investment trust",
                 "Redwood Trust, Inc. is a specialty finance company and REIT.")
    ok, strength = EP._accept_page(real, "Real Estate Investment Trusts",
                                   "Redwood Trust Inc")
    assert ok and strength == EP.STRENGTH_EXACT


def test_accept_rejects_wrong_sibling():
    sibling = _page("Antero Resources", "American energy company",
                    "Antero Resources Corporation is an American oil and natural gas company.")
    ok, strength = EP._accept_page(sibling, "Crude Petroleum & Natural Gas",
                                   "Antero Midstream Corporation")
    assert not ok and strength == EP.STRENGTH_NONE
    # ... even though the industries agree perfectly. Name is the identity test;
    # industry only ever CORROBORATES, it can never substitute for the name.
    assert EP._industry_agrees("Crude Petroleum & Natural Gas",
                               "American energy company", "") is True


def test_accept_rejects_similar_named_subsidiary():
    # a real, legitimate, differently-named affiliate is still the wrong entity
    affiliate = _page("Apollo Commercial Real Estate Finance",
                      "American real estate investment trust",
                      "ARI is a REIT that originates commercial mortgages.")
    ok, _ = EP._accept_page(affiliate, "Investment Advice", "Apollo Global Management")
    assert not ok


def test_accept_rejects_place_case_person_and_disambiguation():
    town = _page("Knife River, Minnesota", "Unincorporated community in Minnesota",
                 "Knife River is an unincorporated community in Lake County.")
    assert not EP._accept_page(town, "Concrete Products", "Knife River Corporation")[0]
    case = _page("Altria Group v. Good", "Legal case",
                 "Altria Group v. Good is a United States Supreme Court case.")
    assert not EP._accept_page(case, "Cigarettes", "Altria Group Inc")[0]
    person = _page("Jean Michel Schlumberger", "French jewellery designer",
                   "Jean Michel Schlumberger was a major French jewellery designer.")
    assert not EP._accept_page(person, "Oil & Gas Field Services, NEC",
                               "Schlumberger Limited")[0]
    ambiguous = _page("AZZ", "Topics referred to by the same term", "", type_="disambiguation")
    assert not EP._accept_page(ambiguous, "Fabricated Metal Products", "AZZ, Inc.")[0]


def test_accept_same_brand_unrelated_organisation_is_withheld():
    """A same-named organisation that is a perfectly real business, but not THIS
    issuer. Organisation-type evidence alone must never be enough."""
    other = _page("Sonic (restaurant chain)", "American fast food chain",
                  "Sonic Drive-In is an American drive-in fast-food chain.")
    ok, _ = EP._accept_page(other, "Semiconductors & Related Devices",
                            "Sonic Automotive Inc")
    assert not ok


def test_accept_fused_token_company_with_first_party_corroboration():
    """The legitimate single-token case: "Eagle Bancorp" -> "EagleBank". One token
    agreed, so it is WEAK — publishable only because the SEC's own industry text
    for the ticker corroborates what the page says it is."""
    bank = _page("EagleBank", "American bank",
                 "EagleBank is an American bank headquartered in Bethesda, Maryland.")
    ok, strength = EP._accept_page(bank, "State Commercial Banks", "Eagle Bancorp, Inc.")
    assert ok and strength == EP.STRENGTH_WEAK
    # strip the first-party corroboration and the SAME page is withheld
    assert not EP._accept_page(bank, None, "Eagle Bancorp, Inc.")[0]
    # ... and an industry that genuinely contradicts also withholds it
    assert not EP._accept_page(bank, "Crude Petroleum & Natural Gas",
                               "Eagle Bancorp, Inc.")[0]
    # NB finance~real_estate is deliberately ADJACENT (mortgage REITs are finance
    # companies), so a REIT SIC does not contradict a bank page — that is the
    # forgiving direction, and it is why RWT is caught on food_service, not on this.


def test_accept_exact_match_is_never_vetoed_by_industry():
    """A full-name match outranks industry corroboration: SEC calls Apple
    "Electronic Computers" while Wikipedia calls it a technology company, and a
    coarse taxonomy mismatch must never withhold a correctly-identified issuer."""
    apple = _page("Apple Inc.", "American multinational technology company",
                  "Apple Inc. is an American multinational technology company.")
    ok, strength = EP._accept_page(apple, "Electronic Computers", "Apple Inc.")
    assert ok and strength == EP.STRENGTH_EXACT


def test_accept_issuer_with_no_safe_page_yields_nothing():
    """Fail-closed is a SUCCESSFUL outcome: no blurb beats another firm's blurb."""
    for page in (_page("Argan (disambiguation)", "", "", type_="disambiguation"),
                 _page("Arginine", "Amino acid", "Arginine is an amino acid."),
                 _page("Sugar Land, Texas", "City in Texas", "Sugar Land is a city.")):
        assert not EP._accept_page(page, "Services-Engineering Services", "Argan, Inc.")[0]


def test_resolution_strength_grades_and_records_provenance():
    S = EP._resolution_strength
    assert S("Microsoft", "Microsoft", "MICROSOFT CORP") == EP.STRENGTH_EXACT
    assert S("Redwood (restaurant)", "Redwood Trust Inc") == EP.STRENGTH_WEAK
    assert S("EagleBank", "Eagle Bancorp, Inc.") == EP.STRENGTH_WEAK
    assert S("Antero Resources", "Antero Midstream") == EP.STRENGTH_NONE
    # >= 2 distinctive tokens all present, no namesake parenthetical
    assert S("Chipotle Mexican Grill", "Chipotle Mexican Grill, Inc.") == EP.STRENGTH_EXACT
    # a corporate parenthetical corroborates rather than demotes
    assert S("Sonic (company)", "Sonic Corp") == EP.STRENGTH_EXACT


def test_parenthetical_qualifier_is_not_corroboration():
    """"(company)" says "the company one" and corroborates. "(benefits company)"
    says "the BENEFITS one" — Wikipedia distinguishing one namesake from another,
    which is the opposite. Accepting any-word-corporate made a private Chicago
    insurer an EXACT match for Trustmark Corp, a Mississippi bank."""
    F = EP._foreign_parenthetical
    assert not F("Sonic (company)", "Sonic Corp")
    assert not F("Aon (corporation)", "Aon plc")
    assert F("Trustmark (benefits company)", "Trustmark Corp")
    assert F("Redwood (restaurant)", "Redwood Trust Inc")
    assert F("Tidewater (marine services)", "Tidewater Inc")
    assert not F("Apple Inc.", "Apple Inc.")           # no parenthetical at all


def test_location_contradiction_is_first_party_and_conservative():
    LC = EP._location_contradicts
    # the collision this exists for: SEC files TRMK at Jackson, MS
    assert LC("JACKSON, MS", "", "Trustmark ranks #69 among Chicago's largest "
                                 "privately held companies in Illinois.")
    # same state named -> no contradiction
    assert not LC("HOUSTON, TX", "", "headquartered in Houston, Texas, U.S.")
    assert not LC("BETHESDA, MD", "", "an American bank headquartered in Bethesda, Maryland.")
    # silence is not contradiction
    assert not LC("JACKSON, MS", "", "A company that makes widgets.")
    assert not LC(None, "", "headquartered in Illinois")
    assert not LC("LONDON, X0", "", "headquartered in Illinois")   # non-US filing address
    # the city matching is enough even when the state is not named
    assert not LC("SCHAUMBURG, IL", "", "based in Schaumburg. Incorporated in Delaware.")


def test_name_collision_needs_the_geographic_tie_breaker():
    """Two real companies, one name, adjacent industries: neither the name test nor
    the coarse industry test can separate them, so the SEC's own filing address
    decides — but ONLY because Wikipedia disambiguated the title."""
    page = _page("Trustmark (benefits company)", "Insurance company",
                 "Trustmark is an insurance company. It ranks #69 among Chicago's "
                 "largest privately held companies in Illinois.")
    assert not EP._accept_page(page, "National Commercial Banks",
                               "Trustmark Corp", hq="JACKSON, MS")[0]
    # the SAME page with a matching filing address is not withheld on location
    assert EP._accept_page(page, "National Commercial Banks",
                           "Trustmark Corp", hq="CHICAGO, IL")[0]
    # and a correctly-resolved disambiguated title survives (SEC files Tidewater's
    # marine business under Water Transportation; the page says petroleum services)
    tidewater = _page("Tidewater (marine services)", "American petroleum service company",
                      "Tidewater, Inc. is a publicly traded international petroleum "
                      "service company headquartered in Houston, Texas.")
    assert EP._accept_page(tidewater, "Water Transportation",
                           "Tidewater Inc", hq="HOUSTON, TX")[0]


def test_no_llm_in_the_resolution_path():
    """Entity linkage is deterministic by contract — never an LLM judgement.

    Structural, not textual: it reads the module's actual imports and string
    literals, so prose ABOUT the rule (this file says "no LLM" in several places)
    can never trip it, and an import that really did appear could never hide in a
    comment."""
    import ast

    src = (Path(__file__).resolve().parent.parent
           / "collectors" / "equity_profile.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned_mods = {"openai", "anthropic", "deepseek", "cohere", "google",
                   "transformers", "litellm", "langchain"}
    assert not (imported & banned_mods), f"resolver imports an LLM client: {imported & banned_mods}"

    # every outbound host is one of the two declared keyless sources
    hosts = {s.value for s in ast.walk(tree)
             if isinstance(s, ast.Constant) and isinstance(s.value, str)
             and s.value.startswith("http")}
    for url in hosts:
        assert ("wikipedia.org" in url or "data.sec.gov" in url), f"unexpected source {url!r}"


def test_stale_resolver_rows_are_eligible_for_corrective_refresh():
    """A blurb accepted by an OLDER rule must not wait out REFRESH_DAYS for its own
    correction — it is re-adjudicated on the next pass."""
    def iso(days):
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    existing = pd.DataFrame(
        {   # ticker:      description,        as_of,  desc_tries, resolver_version
            "OLD_RULE":   ["Wrong-entity text", iso(2), 0.0, float(EP.RESOLVER_VERSION - 1)],
            "CURRENT":    ["Right text",        iso(2), 0.0, float(EP.RESOLVER_VERSION)],
        },
        index=["description", "as_of", "desc_tries", "desc_resolver_version"],
    ).T
    existing.index.name = "ticker"

    seen: list[str] = []

    def wiki(*names, sic_description=None, **kw):
        seen.append(str(names[0]))
        return None, None, None            # Wikipedia refuses everything this pass

    out = _fetch_with_stubs(existing, wiki)
    # the stale-rule row was re-adjudicated; the current-rule row was left alone
    assert any("OLD_RULE" in s for s in seen)
    assert not any("CURRENT" in s for s in seen)
    # and because the refetch found nothing acceptable, the old text is GONE rather
    # than silently carried forward — fail-closed beats a stale wrong entity
    assert EP._cell(out.loc["OLD_RULE", "description"]) is None
    assert out.loc["CURRENT", "description"] == "Right text"


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
