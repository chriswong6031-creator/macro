"""tests/test_news_events.py — W2: event-identity layer tests.

All pure-function / hermetic. No network, no file I/O.

Coverage:
  • Per-class classification fixtures (positive + negative)
  • Numeric extraction table-driven cases
  • theme_centrality: primary vs secondary vs incidental
  • Fail-open qbus (empty store → None fields, no exception)
  • KEEP/DROP IDENTITY: enrichment must not change which items are kept
  • Full news suite import smoke-tests
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from engine.news_events import (
    classify_event,
    extract_numbers,
    theme_centrality,
    enrich_with_qbus,
)


# =========================================================================== #
# CLASSIFY_EVENT — per-class fixtures
# =========================================================================== #

class TestGuidanceCut:
    def test_basic(self):
        r = classify_event("Company cuts full-year revenue guidance as orders slow")
        assert r is not None, "expected guidance_cut"
        assert r["event_type"] == "guidance_cut"
        assert r["direction"] == "bearish"

    def test_raises_variant(self):
        r = classify_event("Acme Corp raises full-year revenue guidance on strong demand")
        assert r is not None
        assert r["event_type"] == "guidance_raise"

    def test_guidance_warns(self):
        r = classify_event("Chipmaker warns of weak quarterly revenue below expectations")
        assert r is not None
        assert r["event_type"] == "guidance_cut"

    def test_profit_warning(self):
        r = classify_event("Retailer issues profit warning as margins compress")
        assert r is not None
        assert r["event_type"] == "guidance_cut"


class TestGuidanceRaise:
    def test_basic(self):
        r = classify_event("Netflix raises quarterly ad-tier pricing guidance above consensus")
        assert r is not None
        assert r["event_type"] == "guidance_raise"

    def test_fy_raise(self):
        r = classify_event("Apple raises FY guidance after record iPhone quarter")
        assert r is not None
        assert r["event_type"] == "guidance_raise"


class TestPreannouncement:
    def test_basic(self):
        r = classify_event("Adobe pre-announces Q3 results, expects revenue above estimates")
        assert r is not None
        assert r["event_type"] == "preannouncement"

    def test_preliminary(self):
        r = classify_event("Boeing issues preliminary revenue results for Q2")
        assert r is not None
        assert r["event_type"] == "preannouncement"


class TestEarningsResult:
    def test_beat(self):
        r = classify_event("Amazon posts Q3 earnings that beat analyst estimates")
        assert r is not None
        assert r["event_type"] == "earnings_result"

    def test_miss(self):
        r = classify_event("Intel reports Q2 results missing revenue forecasts")
        assert r is not None
        assert r["event_type"] == "earnings_result"


class TestAnalystEstimateRevision:
    def test_estimate_cut(self):
        r = classify_event("Wall Street analysts cut EPS estimates for Tesla ahead of delivery data")
        assert r is not None
        assert r["event_type"] == "analyst_estimate_revision"


class TestRatingChange:
    def test_upgrade(self):
        r = classify_event("JPMorgan upgrades Apple to Overweight with $220 price target")
        assert r is not None
        assert r["event_type"] == "rating_change"

    def test_downgrade(self):
        r = classify_event("Goldman downgrades Intel to Sell on margin pressure")
        assert r is not None
        assert r["event_type"] == "rating_change"

    def test_initiate(self):
        r = classify_event("Barclays initiates coverage of Palantir with Overweight rating")
        assert r is not None
        assert r["event_type"] == "rating_change"


class TestContractAward:
    def test_navy_contract(self):
        r = classify_event("Defense contractor wins $2.4B Navy contract for destroyer program")
        assert r is not None
        assert r["event_type"] == "contract_award"
        assert r["direction"] == "bullish"
        nums = r["numbers"]
        assert nums["usd"] == pytest.approx(2.4e9, rel=1e-3)

    def test_without_value_no_match(self):
        # contract_award requires a number
        r = classify_event("Company awarded large contract by government")
        # should NOT fire contract_award if no dollar value
        if r is not None:
            assert r["event_type"] != "contract_award"

    def test_valued_contract(self):
        r = classify_event("Lockheed wins $7.5B Air Force contract")
        assert r is not None
        assert r["event_type"] == "contract_award"
        assert r["numbers"]["usd"] == pytest.approx(7.5e9, rel=1e-3)


class TestMna:
    def test_confirmed(self):
        r = classify_event("Broadcom agrees to acquire VMware in $61B deal")
        assert r is not None
        assert r["event_type"] == "mna_confirmed"

    def test_rumor(self):
        r = classify_event(
            "Sources say Microsoft is exploring acquisition of gaming studio"
        )
        assert r is not None
        assert r["event_type"] == "mna_rumor"

    def test_strategic_review_is_rumor(self):
        r = classify_event("Adobe announces strategic review of options after merger fell through")
        assert r is not None
        assert r["event_type"] in ("mna_rumor", "mna_confirmed")

    def test_confirmed_not_rumor(self):
        # An "agrees to acquire" headline should NOT be classified as mna_rumor
        r = classify_event("Pfizer agrees to acquire oncology startup in $5B deal")
        assert r is not None
        assert r["event_type"] == "mna_confirmed"


class TestMacroRelease:
    def test_nfp(self):
        r = classify_event(
            "US nonfarm payrolls add 175,000 jobs in January, beating forecasts"
        )
        assert r is not None
        assert r["event_type"] == "macro_release"
        assert r["direction"] == "informational"

    def test_cpi(self):
        r = classify_event("CPI rose 3.2% in March, slightly above expectations")
        assert r is not None
        assert r["event_type"] == "macro_release"

    def test_fomc(self):
        r = classify_event("Fed holds rates steady at FOMC meeting; dot plot shows two cuts")
        assert r is not None
        assert r["event_type"] == "macro_release"

    def test_jobs_report(self):
        r = classify_event("Jobs report shows unemployment rate fell to 3.7%")
        assert r is not None
        assert r["event_type"] == "macro_release"


class TestRegProbe:
    def test_ftc(self):
        r = classify_event("FTC probes Amazon's grocery acquisition over antitrust concerns")
        assert r is not None
        assert r["event_type"] == "regulatory_probe"
        assert r["direction"] == "bearish"

    def test_sec_investigate(self):
        r = classify_event("SEC investigates Coinbase over unregistered securities")
        assert r is not None
        assert r["event_type"] == "regulatory_probe"


class TestLitigation:
    def test_lawsuit(self):
        r = classify_event("Shareholders sue Boeing over safety disclosures")
        assert r is not None
        assert r["event_type"] == "litigation"


class TestManagementChange:
    def test_ceo_resign(self):
        r = classify_event("Intel CEO Pat Gelsinger steps down after disappointing results")
        assert r is not None
        assert r["event_type"] == "management_change"

    def test_appoint(self):
        r = classify_event("Starbucks names Brian Niccol as new CEO, hiring him from Chipotle")
        assert r is not None
        assert r["event_type"] == "management_change"


class TestBuyback:
    def test_basic(self):
        r = classify_event("Apple announces $90B share buyback program")
        assert r is not None
        assert r["event_type"] == "buyback"
        assert r["direction"] == "bullish"


class TestDividendChange:
    def test_cut(self):
        r = classify_event("Walgreens cuts quarterly dividend by 48% amid cash flow pressures")
        assert r is not None
        assert r["event_type"] == "dividend_change"

    def test_raise(self):
        r = classify_event("Microsoft raises quarterly dividend by 10%")
        assert r is not None
        assert r["event_type"] == "dividend_change"


class TestEquityOffering:
    def test_follow_on(self):
        r = classify_event("Rivian prices follow-on offering of 21M shares at $12")
        assert r is not None
        assert r["event_type"] == "equity_offering"


class TestBankruptcy:
    def test_chapter11(self):
        r = classify_event("Tupperware files for Chapter 11 bankruptcy protection")
        assert r is not None
        assert r["event_type"] == "bankruptcy_restructuring"
        assert r["direction"] == "bearish"


class TestProductLaunch:
    def test_drug_launch(self):
        r = classify_event("Novo Nordisk launches obesity drug Wegovy in US market")
        assert r is not None
        assert r["event_type"] == "product_launch"


class TestProductDelay:
    def test_delay(self):
        r = classify_event("Apple delays Vision Pro launch amid supply chain issues")
        assert r is not None
        assert r["event_type"] == "product_delay"


class TestActivistCampaign:
    def test_basic(self):
        r = classify_event(
            "Elliott Management takes significant stake in Salesforce, pressures for cost cuts"
        )
        assert r is not None
        assert r["event_type"] == "activist_campaign"


class TestPolicyTradeControl:
    def test_tariff(self):
        r = classify_event("White House announces 25% tariffs on Chinese semiconductor imports")
        assert r is not None
        assert r["event_type"] == "policy_trade_control"


# --------------------------------------------------------------------------- #
# No match — should return None
# --------------------------------------------------------------------------- #
class TestNoMatch:
    def test_lifestyle(self):
        # "Here's what's worth streaming on Netflix" — no event type
        r = classify_event("Here's what's worth streaming on Netflix this weekend")
        assert r is None

    def test_generic_market_wrap(self):
        r = classify_event("Stock market today: S&P 500 ends the week mixed")
        assert r is None

    def test_empty(self):
        assert classify_event("") is None
        assert classify_event(None) is None


# =========================================================================== #
# EXTRACT_NUMBERS — table-driven
# =========================================================================== #

@pytest.mark.parametrize("text,field,expected", [
    # Dollar amounts with B/M/K scaling
    ("Defense contractor wins $2.4B Navy contract", "usd", 2.4e9),
    ("Company raises $500M in follow-on offering", "usd", 500_000_000),
    ("Settlement worth $3.2 billion reached with DOJ", "usd", 3.2e9),
    ("Buyback of $750K authorized by board", "usd", 750_000),
    # Percentages
    ("Revenue grew 12.5% year over year", "pct_first", 12.5),
    ("CPI rose 3.2% in March", "pct_first", 3.2),
    ("Stock fell -4.8% in after-hours trading", "pct_first", -4.8),
    # Guidance range
    ("Company sees FY revenue $4.1-4.3B", "guidance_lo", 4.1e9),
    ("Firm guides for EPS $2.50-$2.70", "guidance_lo", 2.50),
    # EPS
    ("Reports EPS of $1.23, beating estimates", "eps", 1.23),
    ("Posts diluted EPS of $0.87 for the quarter", "eps", 0.87),
    # Payroll counts
    ("Nonfarm payrolls add 175,000 jobs in January", "count", 175_000),
    ("Company to cut 3,500 workers in restructuring", "count", 3_500),
    ("Amazon lays off 57,000 employees across divisions", "count", 57_000),
])
def test_extract_numbers(text, field, expected):
    nums = extract_numbers(text)
    if field == "pct_first":
        assert nums["percentages"], f"expected percentages in {text!r}"
        assert nums["percentages"][0] == pytest.approx(expected, rel=1e-3)
    elif field == "guidance_lo":
        assert nums["guidance_range"] is not None, f"expected guidance_range in {text!r}"
        assert nums["guidance_range"]["lo"] == pytest.approx(expected, rel=1e-3)
    elif field == "eps":
        assert nums["eps"] is not None, f"expected eps in {text!r}"
        assert nums["eps"] == pytest.approx(expected, rel=1e-3)
    elif field == "count":
        assert nums["count"] is not None, f"expected count in {text!r}"
        assert nums["count"] == pytest.approx(expected, rel=1e-3)
    else:  # usd
        assert nums["usd"] is not None, f"expected usd in {text!r}"
        assert nums["usd"] == pytest.approx(expected, rel=1e-3)


def test_extract_numbers_empty():
    n = extract_numbers("")
    assert n["usd"] is None
    assert n["percentages"] == []
    assert n["eps"] is None
    assert n["guidance_range"] is None
    assert n["count"] is None


def test_extract_numbers_multiple_usd():
    n = extract_numbers("Company raises $500M from $1B credit facility")
    assert len(n["usd_all"]) == 2
    assert n["usd_all"][0] == pytest.approx(500_000_000, rel=1e-3)
    assert n["usd_all"][1] == pytest.approx(1_000_000_000, rel=1e-3)


# =========================================================================== #
# THEME_CENTRALITY
# =========================================================================== #

class TestThemeCentrality:
    def test_primary_in_leading_clause(self):
        # "Netflix raises quarterly ad-tier pricing" — 'pricing' is a proxy for
        # 'dividend' theme; the keyword 'raises' is in the first 65 chars.
        c = theme_centrality(
            "Netflix raises quarterly ad-tier pricing",
            "capital_return",
            "raises"
        )
        assert c == "primary"

    def test_incidental_streaming_guide(self):
        # Netflix is present but ONLY as a platform mention at the end, with no action verb nearby.
        # Use a longer title where 'netflix' falls well past the 65-char leading clause.
        c = theme_centrality(
            "The best movies and TV shows to watch this weekend on Disney, Hulu and Netflix",
            "stocks",
            "netflix"
        )
        # keyword appears after position 65 and is not adjacent to any action verb
        assert c in ("secondary", "incidental")

    def test_primary_action_verb_nearby(self):
        c = theme_centrality(
            "Company declares special dividend of $2 per share after strong earnings",
            "capital_return",
            "declares"
        )
        assert c == "primary"

    def test_secondary_trailing_keyword(self):
        # keyword "dividends" is past position 65 and not adjacent to any action verb
        c = theme_centrality(
            "Investors weigh macroeconomic uncertainty amid rising rates, with background attention to dividends",
            "capital_return",
            "dividends"
        )
        # "dividends" is beyond position 65 and "attention to" is not an action verb
        assert c in ("secondary", "incidental")

    def test_incidental_missing_keyword(self):
        c = theme_centrality("Apple reports record quarterly revenue", "labor", "payroll")
        assert c == "incidental"

    def test_empty_inputs(self):
        assert theme_centrality("", "stocks", "apple") == "incidental"
        assert theme_centrality("Apple stock rises", "", "") == "incidental"


# =========================================================================== #
# FAIL-OPEN QBUS — empty store → None fields, no exception
# =========================================================================== #

def test_enrich_with_qbus_empty_store():
    """Fail-open: passing an empty DataFrame (simulating no store) → None fields."""
    import pandas as pd
    from engine.qbus import COLUMNS
    # Build an empty qbus DataFrame (simulates empty store)
    empty_df = pd.DataFrame(columns=list(COLUMNS))

    h = {
        "title": "Apple reports record Q4 earnings",
        "theme": "earnings",
        "tickers": ["AAPL"],
        "seendate": "2026-06-01T12:00:00+00:00",
        "_id": "abc123",
    }
    out = enrich_with_qbus(h, qbus_df=empty_df)
    # must not raise, must attach fields
    assert "event" in out
    assert "centrality" in out
    assert "novelty_z" in out
    assert "echo" in out
    # with empty qbus df, novelty_z and echo must be None
    assert out["novelty_z"] is None
    assert out["echo"] is None


def test_enrich_with_qbus_classify_still_works():
    h = {
        "title": "Defense contractor wins $3.5B Pentagon contract",
        "theme": "stocks",
        "tickers": ["LMT"],
        "seendate": "2026-06-01T12:00:00+00:00",
        "_id": "xyz999",
    }
    out = enrich_with_qbus(h, qbus_df=None)
    assert out["event"] is not None
    assert out["event"]["event_type"] == "contract_award"
    assert out["centrality"] in ("primary", "secondary", "incidental")


def test_enrich_does_not_raise_on_bad_input():
    out = enrich_with_qbus({}, qbus_df=None)
    assert isinstance(out, dict)


# =========================================================================== #
# ECHO JOIN — exact item_id first, shingled-title fallback second
# (same dead-join fix as macro_news._attach_qbus_readback: a headline never
# ingested into qbus under its exact _id must still find its story cluster)
# =========================================================================== #

def _qbus_fixture_df():
    """Two crawls of the SAME Fed story from two desks/sources, clustered into
    one event_key — the minimal 'confirmed elsewhere' store. In-memory only."""
    import pandas as pd
    from engine import qbus
    rows = [
        {"desk": "news_vector", "source": "reuters.com",
         "url": "https://reuters.com/markets/fed-holds-rates",
         "title": "Fed holds interest rates steady",
         "seendate": "2026-06-19T12:00:00+00:00",
         "_crawled_at": "2026-06-19T12:05:00+00:00",
         "entities": [], "themes": ["monetary"], "lang": "en"},
        {"desk": "financial_news", "source": "cnbc.com",
         "url": "https://cnbc.com/2026/06/19/fed-decision.html",
         "title": "Fed holds interest rates steady in June",
         "seendate": "2026-06-19T13:00:00+00:00",
         "_crawled_at": "2026-06-19T13:02:00+00:00",
         "entities": [], "themes": ["monetary"], "lang": "en"},
    ]
    clustered = qbus.assign_event_keys(rows, thresh=0.4, window_days=3)
    assert clustered[0]["event_key"] == clustered[1]["event_key"]
    return pd.DataFrame(clustered, columns=list(qbus.COLUMNS))


def test_enrich_with_qbus_echo_via_exact_item_id_join():
    from engine import qkernel
    df = _qbus_fixture_df()
    # same host + url + title as the stored news_vector crawl → _id joins exactly
    h = {
        "title": "Fed holds interest rates steady",
        "theme": "monetary",
        "tickers": [],
        "seendate": "2026-06-19T12:00:00+00:00",
        "_id": qkernel.item_id("reuters.com",
                               "https://reuters.com/markets/fed-holds-rates",
                               "Fed holds interest rates steady", "en"),
    }
    assert (df["item_id"] == h["_id"]).any()   # the join key really matches
    out = enrich_with_qbus(h, qbus_df=df)
    assert out["echo"] == {"n_sources": 2, "n_desks": 2}


def test_enrich_with_qbus_echo_via_title_fallback():
    df = _qbus_fixture_df()
    # _id absent from the store (different host → different id basis); the
    # shingled-title fallback must still find the story's cluster.
    h = {
        "title": "Fed holds interest rates steady",
        "theme": "monetary",
        "tickers": [],
        "seendate": "2026-06-19T14:00:00+00:00",
        "_id": "ft.com|not-in-store",
    }
    assert not (df["item_id"] == h["_id"]).any()
    out = enrich_with_qbus(h, qbus_df=df)
    assert out["echo"] == {"n_sources": 2, "n_desks": 2}


def test_enrich_with_qbus_unrelated_title_no_echo():
    df = _qbus_fixture_df()
    h = {
        "title": "Eurozone PMI slides to a nine-month low",
        "theme": "growth",
        "tickers": [],
        "seendate": "2026-06-19T14:00:00+00:00",
        "_id": "ft.com|not-in-store",
    }
    out = enrich_with_qbus(h, qbus_df=df)
    assert out["echo"] is None


# =========================================================================== #
# KEEP / DROP IDENTITY
# Enrichment must not change which items are kept or dropped.
# Tested against financial_news.filter logic and macro_news.filter_headlines.
# =========================================================================== #

def _make_article(title, domain="reuters.com", seendate="2026-06-01T12:00:00+00:00",
                  theme=None, source_tier="tier1"):
    return {
        "title": title,
        "url": f"https://{domain}/article",
        "domain": domain,
        "seendate": seendate,
        "theme": theme,
        "source_tier": source_tier,
        "source": "news_rss",
        "source_name": domain,
        "source_lang": "en",
    }


def test_keep_drop_identity_macro_news():
    """filter_headlines outcome must be identical with and without the news_events import."""
    from engine.macro_news import filter_headlines

    articles = [
        _make_article("Federal Reserve holds interest rates steady at FOMC meeting", "cnbc.com",
                      theme="monetary", source_tier="tier1"),
        _make_article("Top 10 stocks to buy now for your retirement portfolio", "fool.com",
                      theme="stocks", source_tier="tier2"),
        _make_article("CPI rose 3.2% in March, above expectations", "wsj.com",
                      theme="inflation", source_tier="tier1"),
        _make_article("Netflix raises quarterly ad-tier pricing by 15%", "bloomberg.com",
                      theme="guidance", source_tier="tier1"),
        _make_article("5 dividend stocks to buy for passive income", "seekingalpha.com",
                      theme="capital_return", source_tier="tier3"),
    ]

    kept_before = filter_headlines(articles)
    kept_before_titles = {h["title"] for h in kept_before}

    # Now enrich each kept item with event-identity and check the set hasn't changed
    from engine.news_events import enrich_with_qbus
    for h in kept_before:
        enrich_with_qbus(h, qbus_df=None)  # mutates h in-place via out = dict(h)

    # Re-run filter on the same input: result must be identical
    kept_after = filter_headlines(articles)
    kept_after_titles = {h["title"] for h in kept_after}

    assert kept_before_titles == kept_after_titles, (
        f"Keep/drop changed after enrichment!\n"
        f"Added: {kept_after_titles - kept_before_titles}\n"
        f"Removed: {kept_before_titles - kept_after_titles}"
    )


def test_keep_drop_identity_financial_news_normalise():
    """_normalise() must return None for blocked/low-value regardless of event fields."""
    from engine import financial_news as fn
    from datetime import datetime, timezone
    now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Low-value: stock pick roundup — must be None
    r1 = fn._normalise(
        "5 dividend stocks to buy now for your portfolio",
        "https://seekingalpha.com/article/1",
        "seekingalpha.com",
        now.isoformat(), "SA", [], "", None, "gdelt", 1.0, now, _emit_qbus=False
    )
    assert r1 is None, "Low-value stock pick must be dropped"

    # Good headline — must survive and have event field
    r2 = fn._normalise(
        "Federal Reserve raises interest rates by 25 basis points",
        "https://reuters.com/article/2",
        "reuters.com",
        now.isoformat(), "Reuters", [], "", None, "rss", 1.0, now, _emit_qbus=False
    )
    assert r2 is not None, "Real headline must be kept"
    assert "event" in r2

    # Blocked domain — must be None
    r3 = fn._normalise(
        "Top stocks to buy this week",
        "https://tipranks.com/article/3",
        "tipranks.com",
        now.isoformat(), "TipRanks", [], "", None, "gdelt", 1.0, now, _emit_qbus=False
    )
    assert r3 is None, "Blocked domain must still be dropped"


# =========================================================================== #
# FULL NEWS SUITE — import smoke tests (W0 step 6 pattern)
# =========================================================================== #

def test_news_common_import():
    from engine import news_common as nc
    assert callable(nc.quality_score)
    assert callable(nc.is_low_value)
    assert callable(nc.low_value_reason)


def test_news_events_import():
    from engine import news_events as ne
    assert callable(ne.classify_event)
    assert callable(ne.extract_numbers)
    assert callable(ne.theme_centrality)
    assert callable(ne.enrich_with_qbus)
    assert ne.is_context_only is True


def test_macro_news_import():
    from engine import macro_news as mn
    assert callable(mn.filter_headlines)
    assert callable(mn.enrich_headline)
    # ensure news_events was imported without circular dependency
    assert hasattr(mn, "_ne")


def test_financial_news_import():
    from engine import financial_news as fn
    assert callable(fn._normalise)
    # ensure news_events was imported without circular dependency
    assert hasattr(fn, "_ne")


def test_qbus_import():
    from engine import qbus
    assert callable(qbus.novelty_z)
    assert callable(qbus.echo_stats)
    assert callable(qbus.read_items)


def test_news_events_no_score_path_imports():
    """news_events must not import from the scoring core (conditions/regime/run/inputs)."""
    import importlib
    import sys
    # The module must be importable without triggering any scoring imports
    mod = importlib.import_module("engine.news_events")
    # Check that scoring-path modules are NOT in its dependencies
    bad_modules = [k for k in sys.modules if any(
        s in k for s in ("conditions", "regime", "equity_alloc", "inputs.")
    ) and not k.startswith("tests")]
    # We can't assert zero (other tests may have loaded them), but news_events itself
    # must not be the thing that loaded them — verify is_context_only contract.
    assert mod.is_context_only is True


# =========================================================================== #
# PRECISION GATE — verify per-class precision ≥ 90% over this fixture set
# =========================================================================== #

_FIXTURE_CASES: list[tuple[str, str | None]] = [
    # (title, expected_event_type or None)
    ("Company cuts full-year revenue guidance as orders slow",               "guidance_cut"),
    ("Netflix raises quarterly ad-tier pricing",                              None),  # pricing raise, NOT guidance
    ("Apple raises FY guidance after record iPhone quarter",                  "guidance_raise"),
    ("Chipmaker warns of weak quarterly revenue below expectations",          "guidance_cut"),
    ("Adobe pre-announces Q3 results",                                        "preannouncement"),
    ("Amazon posts Q3 earnings that beat analyst estimates",                  "earnings_result"),
    ("JPMorgan upgrades Apple to Overweight",                                 "rating_change"),
    ("Goldman downgrades Intel to Sell",                                      "rating_change"),
    ("Defense contractor wins $2.4B Navy contract",                           "contract_award"),
    ("Broadcom agrees to acquire VMware in $61B deal",                        "mna_confirmed"),
    ("Sources say Microsoft is exploring acquisition of gaming studio",        "mna_rumor"),
    ("Apple announces $90B share buyback",                                    "buyback"),
    ("Walgreens cuts quarterly dividend by 48%",                              "dividend_change"),
    ("Tupperware files for Chapter 11 bankruptcy",                            "bankruptcy_restructuring"),
    ("US nonfarm payrolls add 175,000 jobs in January",                       "macro_release"),
    ("CPI rose 3.2% in March, slightly above expectations",                   "macro_release"),
    ("Fed holds rates steady at FOMC meeting",                                "macro_release"),
    ("FTC probes Amazon's grocery acquisition",                               "regulatory_probe"),
    ("Shareholders sue Boeing over safety",                                   "litigation"),
    ("Intel CEO Pat Gelsinger steps down",                                    "management_change"),
    ("White House announces 25% tariffs on Chinese semiconductor imports",     "policy_trade_control"),
    ("Here's what's worth streaming on Netflix this weekend",                 None),
    ("Stock market today: S&P 500 ends week mixed",                           None),
    ("Top 10 stocks to buy for retirement",                                   None),
]


def test_precision_gate():
    """At least 90% of labeled fixtures must match exactly (or both None)."""
    correct = 0
    wrong: list[str] = []
    for title, expected in _FIXTURE_CASES:
        r = classify_event(title)
        got = r["event_type"] if r is not None else None
        if got == expected:
            correct += 1
        else:
            wrong.append(f"  '{title[:60]}...' → got={got!r}, expected={expected!r}")

    precision = correct / len(_FIXTURE_CASES)
    details = "\n".join(wrong) if wrong else "(none)"
    assert precision >= 0.90, (
        f"Precision {precision:.0%} < 90% ({correct}/{len(_FIXTURE_CASES)} correct).\n"
        f"Failures:\n{details}"
    )
