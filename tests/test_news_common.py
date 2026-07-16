"""Pure-function tests for engine/news_common.py — no network.

Covers: source_tier, quality_score, clickbait_penalty, recency_weight,
event_id/norm_title, build_entity_map, match_entities, tickers_to_groups.
All assertions use plain assert. Deterministic now=datetime(2026,6,19,tzinfo=utc).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import news_common as nc  # noqa: E402

_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# source_tier
# --------------------------------------------------------------------------- #
def test_source_tier_tier1():
    assert nc.source_tier("reuters.com") == 1
    assert nc.source_tier("finance.bloomberg.com") == 1
    assert nc.source_tier("wsj.com") == 1
    assert nc.source_tier("cnbc.com") == 1


def test_source_tier_tier2():
    assert nc.source_tier("forbes.com") == 2
    assert nc.source_tier("fortune.com") == 2
    assert nc.source_tier("axios.com") == 2


def test_source_tier_central_banks_tier1():
    # primary central-bank sources rank as wires (trusted on source alone)
    assert nc.source_tier("federalreserve.gov") == 1
    assert nc.source_tier("www.ecb.europa.eu") == 1
    assert nc.source_tier("boj.or.jp") == 1


def test_source_tier_added_business_press_tier2():
    # outlets matched from Perplexity Finance's source list
    assert nc.source_tier("tradingeconomics.com") == 2
    assert nc.source_tier("economictimes.indiatimes.com") == 2
    assert nc.source_tier("moneycontrol.com") == 2
    # the ET subdomain is pinned — general Times of India must NOT be allowlisted
    assert nc.source_tier("timesofindia.indiatimes.com") == 0


def test_source_tier_tier3():
    assert nc.source_tier("benzinga.com") == 3
    assert nc.source_tier("seekingalpha.com") == 3
    assert nc.source_tier("yahoo.com") == 3


def test_source_tier_unknown():
    assert nc.source_tier("randomspam.xyz") == 0
    assert nc.source_tier("") == 0
    assert nc.source_tier("notinanylist.blog") == 0


# --------------------------------------------------------------------------- #
# norm_title / event_id
# --------------------------------------------------------------------------- #
def test_norm_title_strips_and_lowercases():
    assert nc.norm_title("  Hello, World!  ") == "hello world"
    assert nc.norm_title("NVDA Earnings Beat!!!") == "nvda earnings beat"
    assert nc.norm_title("") == ""
    assert nc.norm_title(None) == ""


def test_event_id_stable_and_hex():
    a = nc.event_id("Fed holds rates steady", "reuters.com")
    b = nc.event_id("Fed holds rates steady", "reuters.com")
    assert a == b
    assert len(a) == 16
    assert all(c in "0123456789abcdef" for c in a)


def test_event_id_case_and_whitespace_invariant():
    a = nc.event_id("Fed  HOLDS Rates Steady!!!", "Reuters.com")
    b = nc.event_id("fed holds rates steady", "reuters.com")
    assert a == b


def test_event_id_domain_participates():
    a = nc.event_id("Same title here", "reuters.com")
    b = nc.event_id("Same title here", "cnbc.com")
    assert a != b


# --------------------------------------------------------------------------- #
# clickbait_penalty
# --------------------------------------------------------------------------- #
def test_clickbait_penalty_clean_title():
    assert nc.clickbait_penalty("Fed holds rates as inflation cools") == 0.0
    assert nc.clickbait_penalty("NVDA earnings beat estimates by 12%") == 0.0


def test_clickbait_penalty_listicle():
    # "7 stocks" is in _CLICKBAIT -> 0.18; listicle regex also triggers -> +0.15
    pen = nc.clickbait_penalty("7 stocks to buy now")
    assert pen > 0.0
    # "3 reasons" => listicle match
    pen2 = nc.clickbait_penalty("3 reasons to sell this stock")
    assert pen2 > 0.0


def test_clickbait_penalty_capped():
    # Max is 0.45 even with many matches
    pen = nc.clickbait_penalty("7 stocks to buy now skyrocket millionaire get rich")
    assert pen <= 0.45


def test_clickbait_penalty_question_mark():
    pen = nc.clickbait_penalty("Should you buy NVDA now?")
    assert pen > 0.0  # short question mark title -> penalty


# --------------------------------------------------------------------------- #
# recency_weight
# --------------------------------------------------------------------------- #
def test_recency_weight_fresh():
    iso = "2026-06-19T12:00:00+00:00"   # same as _NOW
    w = nc.recency_weight(iso, now=_NOW, half_life_h=36.0)
    assert abs(w - 1.0) < 0.01


def test_recency_weight_half_life():
    # 36 hours before _NOW -> weight ~0.5
    from datetime import timedelta
    past = (_NOW - timedelta(hours=36)).isoformat()
    w = nc.recency_weight(past, now=_NOW, half_life_h=36.0)
    assert abs(w - 0.5) < 0.02


def test_recency_weight_unknown_date():
    # Garbled/empty date -> 0.4 neutral fallback
    assert nc.recency_weight("", now=_NOW) == 0.4
    assert nc.recency_weight("not-a-date", now=_NOW) == 0.4
    assert nc.recency_weight(None, now=_NOW) == 0.4


def test_recency_weight_old_article():
    # 1 week old -> well below 0.5
    from datetime import timedelta
    old = (_NOW - timedelta(days=7)).isoformat()
    w = nc.recency_weight(old, now=_NOW, half_life_h=36.0)
    assert w < 0.1


# --------------------------------------------------------------------------- #
# quality_score
# --------------------------------------------------------------------------- #
def test_quality_score_tier1_high():
    # Fresh wire story, full relevance, no clickbait -> high score
    iso = "2026-06-19T12:00:00+00:00"
    q = nc.quality_score("Fed cuts rates by 50bp", "reuters.com",
                         seendate_iso=iso, relevance=1.0, now=_NOW)
    assert q >= 60


def test_quality_score_tier0_drops_to_zero():
    # Tier-0 domain without override -> 0
    iso = "2026-06-19T12:00:00+00:00"
    q = nc.quality_score("Some headline", "randomspam.xyz",
                         seendate_iso=iso, relevance=1.0, now=_NOW)
    assert q == 0


def test_quality_score_tier_override_for_pr_wire():
    # tier=3 override makes a tier-0 domain non-zero (PR-wire floor)
    iso = "2026-06-19T12:00:00+00:00"
    q = nc.quality_score("Company announces earnings", "businesswire.com",
                         seendate_iso=iso, relevance=1.0, now=_NOW, tier=3)
    assert q > 0


def test_quality_score_tier1_beats_tier3():
    iso = "2026-06-19T12:00:00+00:00"
    q1 = nc.quality_score("Markets rally on Fed news", "reuters.com",
                          seendate_iso=iso, relevance=1.0, now=_NOW)
    q3 = nc.quality_score("Markets rally on Fed news", "benzinga.com",
                          seendate_iso=iso, relevance=1.0, now=_NOW)
    assert q1 > q3


def test_quality_score_clickbait_penalised():
    iso = "2026-06-19T12:00:00+00:00"
    q_clean = nc.quality_score("Fed raises rates 50bp", "bloomberg.com",
                               seendate_iso=iso, relevance=1.0, now=_NOW)
    q_cb = nc.quality_score("7 stocks to buy now skyrocket", "bloomberg.com",
                             seendate_iso=iso, relevance=1.0, now=_NOW)
    assert q_clean > q_cb


# --------------------------------------------------------------------------- #
# build_entity_map
# --------------------------------------------------------------------------- #
def test_build_entity_map_structure():
    emap = nc.build_entity_map()
    assert set(emap.keys()) >= {"baskets", "tickers", "sectors", "mag7", "aliases"}


def test_build_entity_map_nvda_in_mag7():
    emap = nc.build_entity_map()
    assert "NVDA" in emap["mag7"]


def test_build_entity_map_sectors_has_11_gics():
    emap = nc.build_entity_map()
    gics = {"XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"}
    assert gics <= set(emap["sectors"].keys())


def test_build_entity_map_nvda_tickers_entry():
    emap = nc.build_entity_map()
    # NVDA must appear in tickers (seeded by MAG7 at build time)
    assert "NVDA" in emap["tickers"]
    info = emap["tickers"]["NVDA"]
    assert info.get("is_mag7") is True
    # NVDA should be in at least one basket
    assert len(info.get("baskets", [])) >= 1


def test_build_entity_map_nvda_in_mag7_basket():
    emap = nc.build_entity_map()
    info = emap["tickers"].get("NVDA", {})
    # At least one basket key contains 'mag7' or NVDA is expected in AI/semis basket
    baskets = info.get("baskets", [])
    assert len(baskets) >= 1, "NVDA must belong to at least one basket"


# --------------------------------------------------------------------------- #
# match_entities
# --------------------------------------------------------------------------- #
def test_match_entities_ticker_symbol():
    emap = nc.build_entity_map()
    hits = nc.match_entities("NVDA reported strong earnings today", emap)
    assert "NVDA" in hits


def test_match_entities_alias():
    emap = nc.build_entity_map()
    hits = nc.match_entities("Nvidia beats estimates on AI chip demand", emap)
    assert "NVDA" in hits


def test_match_entities_aapl_alias():
    emap = nc.build_entity_map()
    hits = nc.match_entities("Apple reported iPhone sales rose 10%", emap)
    assert "AAPL" in hits


def test_match_entities_stopwords_not_tagged():
    emap = nc.build_entity_map()
    # GDP, FED, ETF, US, AI are in _TICKER_STOPWORDS and must never appear as tickers
    hits = nc.match_entities("GDP data shows the FED cut ETF US AI policy rates", emap)
    assert "GDP" not in hits
    assert "FED" not in hits
    assert "ETF" not in hits
    assert "US" not in hits
    assert "AI" not in hits


def test_match_entities_empty_text():
    emap = nc.build_entity_map()
    hits = nc.match_entities("", emap)
    assert hits == set()


# --------------------------------------------------------------------------- #
# tickers_to_groups
# --------------------------------------------------------------------------- #
def test_tickers_to_groups_nvda():
    emap = nc.build_entity_map()
    grp = nc.tickers_to_groups(["NVDA"], emap)
    assert grp["mag7"] is True
    assert len(grp["baskets"]) >= 1


def test_tickers_to_groups_unknown_ticker():
    emap = nc.build_entity_map()
    grp = nc.tickers_to_groups(["XXXXUNKNOWN"], emap)
    assert grp["baskets"] == []
    assert grp["sectors"] == []
    assert grp["mag7"] is False


def test_tickers_to_groups_sorted_output():
    emap = nc.build_entity_map()
    grp = nc.tickers_to_groups(["AAPL", "MSFT", "NVDA"], emap)
    assert grp["baskets"] == sorted(grp["baskets"])
    assert grp["sectors"] == sorted(grp["sectors"])


# --------------------------------------------------------------------------- #
# blocklist (is_blocked) + tier interaction
# --------------------------------------------------------------------------- #
def test_is_blocked_tipranks():
    assert nc.is_blocked("tipranks.com") is True
    assert nc.is_blocked("www.tipranks.com") is True
    assert nc.is_blocked("smartreads.tipranks.com") is True


def test_is_blocked_others_false():
    assert nc.is_blocked("cnbc.com") is False
    assert nc.is_blocked("reuters.com") is False
    assert nc.is_blocked("") is False


def test_blocked_domain_is_tier0():
    # TipRanks was tier-3; the blocklist now forces it to tier-0 (dropped).
    assert nc.source_tier("tipranks.com") == 0
    # And quality_score returns 0 for a blocked domain regardless of freshness.
    assert nc.quality_score("Some headline", "tipranks.com", _NOW.isoformat(), now=_NOW) == 0


# --------------------------------------------------------------------------- #
# low-value detection (is_low_value) — HARD DROP
# --------------------------------------------------------------------------- #
def test_is_low_value_stock_pick_roundups():
    # The exact CNBC-hosted TipRanks columns that surfaced as the #1 story.
    assert nc.is_low_value(
        "Top Wall Street analysts like these 3 dividend stocks for solid returns") is True
    assert nc.is_low_value(
        "Top Wall Street analysts are confident about the growth prospects of these 3 stocks") is True
    # General advertorial listicle formats.
    for t in ["5 stocks to buy now", "7 AI stocks that could soar in 2026",
              "The best dividend stocks for retirement", "Where to invest $10,000 right now",
              "2 growth stocks to buy hand over fist", "Analysts love these 3 chip stocks",
              "Stock picks: our favorites for the second half"]:
        assert nc.is_low_value(t) is True, t


def test_is_low_value_preview_calendar_movers_roundups():
    # The exact Seeking Alpha / CNBC content-free roundups that surface as top
    # stories: calendar previews, movers lists, week-ahead previews, market wraps.
    for t in [
        "Here are the major earnings before the open Monday",          # reported case
        "Major earnings before the open: Nike, FedEx and more",
        "Stocks making the biggest moves premarket: Nvidia, Tesla and more",
        "Stocks making the biggest moves midday",
        "Biggest movers: tech leads, energy lags",
        "Notable premarket gainers and losers",
        "Earnings calendar: Micron, Nike and more on deck",
        "Economic calendar: key data this week",
        "Earnings preview: what to expect from Nvidia",
        "What to watch in the stock market this week",
        "5 things to know before the stock market opens Monday",
        "The week ahead: CPI and a busy earnings calendar",
        "Wall Street wrap: stocks end mixed",
        "Stock market today: Live updates",
        "Trending tickers: GME, AMC in focus",
        "Stocks to watch on Tuesday",                                  # caught by _ROUNDUP_RE
        "Here are the day's biggest winners and losers",
        # 'things to watch' previews — adjectives between the count and the noun
        "Here are 3 big things to watch in the stock market this coming week",
        "5 things to watch in markets this week",
        "Things to know before the opening bell",
        # crypto/asset 'price prediction' SEO spam (multi-year forecast advertorials)
        "PancakeSwap (CAKE) Price Prediction: 2025, 2026, 2030",
        "Arweave (AR) Price Prediction: 2025, 2026, 2030",
        "Toncoin (TON) Price Prediction 2025, 2026, 2027-2030",
        "Myro (MYRO) Price Prediction: 2025, 2026, 2030",
    ]:
        assert nc.is_low_value(t) is True, t


def test_is_low_value_preview_keeps_real_single_event_news():
    # Real single-fact stories that LOOK adjacent to the roundup frames must survive.
    for t in [
        "Micron's earnings are a must-watch market event",            # must-watch != what-to-watch
        "Nvidia stock rises after earnings beat estimates",           # 'after earnings' != 'earnings after the bell'
        "Here's how much the Iran war cost — and how its effects will linger",  # explanatory feature, no list-noun
        "Nvidia earnings due after the bell Wednesday",               # single-name preview, informative
        "Analysts raise Nvidia price target to $200 after earnings",   # price TARGET (real) != price PREDICTION (spam)
        "Investors watch the Fed as inflation cools this week",        # 'watch' but not 'things/what to watch'
        "Fed holds rates as inflation cools",
        "Tech stocks rally as Treasury yields fall",
        "Stocks close higher as Powell signals patience",
        "Apple unveils new AI features at its developer conference",
    ]:
        assert nc.is_low_value(t) is False, t


def test_is_low_value_personal_finance_advice():
    assert nc.is_low_value(
        "I'm spending $170,000 to upgrade my home for my aging parents. Can I get tax breaks?") is True
    assert nc.is_low_value(
        "My mother was co-owner of my grandmother's bank account. Should she share the money?") is True
    # First-person opener WITHOUT a question is NOT dropped (could be real commentary).
    assert nc.is_low_value("I'm a CEO and here's why I'm bullish on AI") is False


def test_is_low_value_pickmill_byline():
    # A trusted outlet (no junk title) re-running a pick-mill column → drop on byline.
    assert nc.is_low_value("Three great companies", author="TipRanks.com Staff") is True
    assert nc.is_low_value("Three great companies", author="Zacks Equity Research") is True
    assert nc.is_low_value("Three great companies", author="Jane Reporter") is False


def test_is_low_value_keeps_real_news():
    for t in ["Brent crude slips as Qatar, Pakistan announce 60-day roadmap",
              "Micron's earnings are a must-watch market event",
              "Wells Fargo new S&P 500 target sends investors clear signal",
              "Nvidia stock rises after earnings beat estimates",
              "Fed holds rates as inflation cools",
              "Tech stocks rally as Treasury yields fall",
              "Wall Street analysts raise their S&P 500 price targets",
              "Magnificent Seven stocks slide as megacap rally stalls"]:
        assert nc.is_low_value(t) is False, t


def test_is_low_value_empty():
    assert nc.is_low_value("") is True
    assert nc.is_low_value(None) is True


# --------------------------------------------------------------------------- #
# F3a: analyst_report_stub (new family 2026-07-16)
# --------------------------------------------------------------------------- #
def test_analyst_report_stub_dropped():
    """Yahoo/Argus batch stubs anchored at '^Analyst Report:' are dropped."""
    assert nc.is_low_value("Analyst Report: AAPL") is True
    assert nc.low_value_reason("Analyst Report: AAPL") == "analyst_report_stub"
    assert nc.is_low_value("Analyst Report: Microsoft (MSFT)") is True


def test_analyst_report_stub_does_not_fire_on_real_analyst_news():
    """Real analyst upgrades, downgrades, and commentary must not be caught."""
    assert nc.is_low_value("JPMorgan upgrades Apple to Overweight") is False
    assert nc.is_low_value("Analyst raises Nvidia price target to $180") is False
    # The word 'analyst' appears mid-title — must not fire anchor match
    assert nc.is_low_value("Wall Street analysts turn bullish on chips") is False


# --------------------------------------------------------------------------- #
# F3b: dividend_declaration_stub (new family 2026-07-16)
# --------------------------------------------------------------------------- #
def test_dividend_stub_drops_microcap_dollar_declarations():
    """Microcap '$N dividend' declarations occupying feed slots must be dropped."""
    assert nc.is_low_value("Smart Sand declares $0.10 dividend") is True
    assert nc.low_value_reason("Smart Sand declares $0.10 dividend") == "dividend_declaration_stub"
    assert nc.is_low_value("Saratoga Investment declares $0.56 dividend") is True


def test_dividend_stub_exempts_megacap_aliases():
    """Titles containing a megacap alias are exempt from the stub filter."""
    assert nc.is_low_value("Apple declares $0.25 quarterly dividend") is False
    assert nc.is_low_value("Microsoft announces $0.94 dividend") is False
    assert nc.is_low_value("Nvidia announces first dividend of $0.10") is False


def test_dividend_stub_keeps_non_dollar_raise_forms():
    """'Apple raises quarterly dividend 4%' has no $amount and is not a stub."""
    assert nc.is_low_value("Apple raises quarterly dividend 4%, announces $110B buyback") is False


def test_dividend_change_stories_kept_even_smallcap():
    """A cut/suspension/raise/special is NEWS even from a non-megacap — the
    change-word guard exempts it from the routine-declaration stub family."""
    assert nc.is_low_value("Ford announces 20% dividend cut") is False
    assert nc.is_low_value("GM announces $2B buyback and cuts dividend") is False
    assert nc.is_low_value("Whirlpool declares $1.75 special dividend") is False
    assert nc.is_low_value("Devon Energy announces $0.22 dividend increase") is False
    # Routine declaration without a change-word still drops.
    assert nc.low_value_reason("Smart Sand declares $0.10 dividend") == "dividend_declaration_stub"


# --------------------------------------------------------------------------- #
# F3c: morning_aggregator (new family 2026-07-16)
# --------------------------------------------------------------------------- #
def test_morning_aggregator_and_more_in_dropped():
    """'… and more in <show name>' teasers are morning-aggregator roundups."""
    assert nc.is_low_value(
        "Grocery sales, United earnings, Anthropic's IPO prep and more in Morning Squawk") is True
    assert nc.low_value_reason(
        "Grocery sales, United earnings, Anthropic's IPO prep and more in Morning Squawk"
    ) == "morning_aggregator"


def test_morning_aggregator_keeps_standalone_show_mention():
    """A real story that merely mentions a show by name is not a teaser."""
    assert nc.is_low_value("Morning Squawk: Powell says rates likely higher for longer") is False
    assert nc.is_low_value("CNBC Squawk Box interview — Fed Chair discusses inflation") is False


def test_morning_aggregator_keeps_and_more_in_line_with():
    """'and more in' followed by ordinary prose (no show/aggregator noun) is NOT
    a teaser — 'in line with' was a verified false-drop in review."""
    assert nc.is_low_value("Fed sees costs rising and more in line with expectations") is False
    assert nc.is_low_value("Housing starts fall, and more in line with the 2019 trend") is False
    # The show-noun form still drops.
    assert nc.low_value_reason(
        "Jobs data, bank earnings and more in today's rundown") == "morning_aggregator"


# --------------------------------------------------------------------------- #
# F4/MN-09: 'what to know' trailing-suffix narrowing
# --------------------------------------------------------------------------- #
def test_what_to_know_trailing_suffix_kept():
    """'... Here's what to know' at the end of a substantive title is NOT a roundup."""
    assert nc.is_low_value("Trump national address tonight. Here's what to know") is False
    assert nc.is_low_value("CPI print surprised. Here is what to know") is False


def test_what_to_know_at_start_still_dropped():
    """'What to watch/know/expect' as the opener of a title is a calendar-preview stub."""
    assert nc.low_value_reason("What to watch this week") == "calendar_preview"
    assert nc.low_value_reason("What to know about the Fed meeting Wednesday") == "calendar_preview"


def test_what_to_expect_after_colon_dropped():
    """'<label>: what to expect from …' is a structural roundup."""
    assert nc.low_value_reason("Earnings preview: what to expect from Nvidia") == "calendar_preview"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
