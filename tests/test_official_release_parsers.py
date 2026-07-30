from __future__ import annotations

from datetime import date

import pytest

from scripts.official_release_parsers import (
    extract_feed_entry,
    parse_actual,
    parse_claims_actual,
    parse_cpi_actual,
    parse_gdp_actual,
    parse_nfp_actual,
    parse_pce_actual,
    parse_ppi_actual,
)


BLS_CPI_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>bls.gov:feed:cpi</id>
  <title>Consumer Price Index</title>
  <entry>
    <title>CPI for all items falls 0.4% in June; gasoline down</title>
    <link href="https://www.bls.gov/news.release/archives/cpi_07142026.htm"/>
    <id>cpi-2026_07_14__07_50_27</id>
    <content>In June, the Consumer Price Index for All Urban Consumers fell 0.4
    percent, seasonally adjusted, and rose 3.5 percent over the last 12 months,
    not seasonally adjusted. The index for all items less food and energy was
    unchanged in June (SA); up 2.6 percent over the year (NSA).</content>
    <published>2026-07-14T07:50:27.969-04:00</published>
  </entry>
  <entry>
    <title>CPI for all items rises 0.5% in May</title>
    <link href="https://www.bls.gov/news.release/archives/cpi_06102026.htm"/>
    <id>cpi-2026_06_10__08_30_00</id>
    <content>In May, the Consumer Price Index for All Urban Consumers rose 0.5
    percent, seasonally adjusted, and rose 4.2 percent over the last 12 months.
    The index for all items less food and energy increased 0.2 percent in May
    (SA); up 2.9 percent over the year (NSA).</content>
    <published>2026-06-10T08:30:00-04:00</published>
  </entry>
</feed>
"""


BEA_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item name="Gross Domestic Product by State">
      <title>Gross Domestic Product by State, 1st Quarter 2026</title>
      <link>https://www.bea.gov/news/2026/gdp-by-state</link>
      <description>State GDP release that must not match the national event.</description>
      <pubDate>Thu, 30 Jul 2026 08:30:00 EDT</pubDate>
    </item>
    <item name="GDP">
      <title>GDP (Advance Estimate), 2nd Quarter 2026</title>
      <link>www.bea.gov/news/2026/gdp-advance-estimate-2nd-quarter-2026</link>
      <guid>www.bea.gov/news/2026/gdp-advance-estimate-2nd-quarter-2026</guid>
      <description>Real gross domestic product (GDP) increased at an annual rate
      of 3.0 percent in the second quarter of 2026.</description>
      <data><main><current><infoDate>Q2 2026</infoDate></current></main></data>
      <pubDate>Thu, 30 Jul 2026 08:30:00 EDT</pubDate>
    </item>
    <item name="Personal Income and Outlays">
      <title>Personal Income and Outlays, June 2026</title>
      <link>https://www.bea.gov/news/2026/personal-income-and-outlays-june-2026</link>
      <guid>https://www.bea.gov/news/2026/personal-income-and-outlays-june-2026</guid>
      <description>Personal income increased in June.</description>
      <data><main><current><infoDate>June 2026</infoDate></current></main></data>
      <pubDate>Thu, 30 Jul 2026 08:30:00 EDT</pubDate>
    </item>
    <item name="GDP">
      <title>GDP (Third Estimate), 1st Quarter 2026</title>
      <link>https://www.bea.gov/news/2026/gdp-third-estimate-1q</link>
      <description>Real GDP increased 2.1 percent.</description>
      <pubDate>Thu, 25 Jun 2026 08:30:00 EDT</pubDate>
    </item>
  </channel>
</rss>
"""


DOL_ETA_LISTING = b"""
<div class="view-content">
  <div class="dol-feed-block">
    <div data-history-node-id="other"
         about="/newsroom/releases/eta/eta20260723-other">
      <p class="dol-date-text">July 23, 2026</p>
      <a href="/newsroom/releases/eta/eta20260723-other">
        <h3><span>Apprenticeship announcement</span></h3>
      </a>
      <div class="field--name-field-press-body"><p>Unrelated release.</p></div>
    </div>
  </div>
  <div class="dol-feed-block">
    <div data-history-node-id="185964"
         about="/newsroom/releases/eta/eta20260723">
      <p class="dol-date-text">July 23, 2026</p>
      <a href=" /newsroom/releases/eta/eta20260723 ">
        <h3><span>Unemployment Insurance Weekly Claims Report</span></h3>
      </a>
      <div class="field--name-field-press-body"><p>In the week ending July 18,
      the advance figure for seasonally adjusted initial claims was 187,000, a
      decrease of 22,000 from the previous week's revised level. The previous
      week's level was revised up by 1,000 from 208,000 to 209,000. The 4-week
      moving average was 207,500, a decrease of 7,250 from the previous week's
      revised average.</p></div>
    </div>
  </div>
</div>
"""


def test_bls_atom_selector_requires_exact_event_date() -> None:
    selected = extract_feed_entry("bls_cpi", BLS_CPI_ATOM, date(2026, 6, 10))

    assert selected is not None
    assert selected["entry_id"] == "cpi-2026_06_10__08_30_00"
    assert selected["source_url"].endswith("cpi_06102026.htm")
    assert selected["source_released_at"] == "2026-06-10T12:30:00+00:00"
    assert selected["reference_period"] == "May 2026"
    assert b"rose 0.5" in selected["body"]
    # A future calendar date must not be paired with the feed's newest item.
    assert extract_feed_entry("bls_cpi", BLS_CPI_ATOM, "2026-08-12") is None


def test_bea_rss_selects_independent_same_day_gdp_and_pce_items() -> None:
    gdp = extract_feed_entry("bea_gdp", BEA_RSS, "2026-07-30")
    pce = extract_feed_entry("bea_pce_rss", BEA_RSS, "2026-07-30")

    assert gdp is not None and pce is not None
    assert gdp["title"] == "GDP (Advance Estimate), 2nd Quarter 2026"
    assert gdp["reference_period"] == "Q2 2026"
    assert gdp["source_url"].startswith("https://www.bea.gov/")
    assert pce["title"] == "Personal Income and Outlays, June 2026"
    assert pce["reference_period"] == "June 2026"
    assert gdp["source_url"] != pce["source_url"]
    assert extract_feed_entry("bea_gdp", BEA_RSS, "2026-07-31") is None


def test_feed_selector_fails_closed_for_bad_input() -> None:
    assert extract_feed_entry("unknown", BLS_CPI_ATOM, "2026-07-14") is None
    assert extract_feed_entry("bls_ppi", BLS_CPI_ATOM, "2026-07-14") is None
    assert extract_feed_entry("bls_cpi", b"<not-closed", "2026-07-14") is None
    assert extract_feed_entry("bls_cpi", BLS_CPI_ATOM, "not-a-date") is None


def test_dol_listing_selector_uses_exact_deterministic_release_path() -> None:
    selected = extract_feed_entry("dol_claims", DOL_ETA_LISTING, "2026-07-23")

    assert selected is not None
    assert selected["entry_id"] == "/newsroom/releases/eta/eta20260723"
    assert selected["source_url"] == (
        "https://www.dol.gov/newsroom/releases/eta/eta20260723"
    )
    assert selected["source_released_at"] is None
    assert selected["title"] == "Unemployment Insurance Weekly Claims Report"
    actual = parse_actual("claims", selected["body"])
    assert actual is not None
    assert actual["initial_claims"] == 187_000
    assert actual["reference_period"] == "July 18, 2026"
    assert extract_feed_entry("dol_claims", DOL_ETA_LISTING, "2026-07-30") is None


def test_cpi_parser_extracts_headline_and_core_changes() -> None:
    selected = extract_feed_entry("bls_cpi", BLS_CPI_ATOM, "2026-07-14")
    assert selected is not None

    actual = parse_cpi_actual(selected["body"])

    assert actual is not None
    assert actual["headline_mom"] == -0.4
    assert actual["headline_yoy"] == 3.5
    assert actual["core_mom"] == 0.0
    assert actual["core_yoy"] == 2.6
    assert actual["reference_period"] == "June 2026"
    assert [row["metric_id"] for row in actual["metrics"]] == [
        "cpi_headline_mom",
        "cpi_core_mom",
        "cpi_headline_yoy",
        "cpi_core_yoy",
    ]
    assert all(row["period"] == "June 2026" for row in actual["metrics"])
    assert actual["headline_en"] == "CPI -0.4% m/m; core +0.0%"
    assert actual["headline_zh"]


PPI_ENTRY = b"""
PPI for final demand declines 0.3% in June; goods fall 1.4%, services increase 0.2%
The Producer Price Index for final demand fell 0.3 percent in June. Prices for
final demand goods decreased 1.4 percent, and the index for final demand services
moved up 0.2 percent. Prices for final demand increased 5.5 percent for the
12 months ended in June.
"""


def test_ppi_parser_extracts_goods_services_and_yearly_change() -> None:
    actual = parse_ppi_actual(PPI_ENTRY)

    assert actual is not None
    assert actual["headline_mom"] == -0.3
    assert actual["goods_mom"] == -1.4
    assert actual["services_mom"] == 0.2
    assert actual["headline_yoy"] == 5.5
    assert actual["reference_period"] is None
    assert {row["metric_id"] for row in actual["metrics"]} == {
        "ppi_headline_mom",
        "ppi_headline_yoy",
        "ppi_goods_mom",
        "ppi_services_mom",
    }
    assert "PPI -0.3%" in actual["headline_en"]
    assert actual["summary_zh"]


@pytest.mark.parametrize(
    ("release", "payroll_change", "unemployment_rate"),
    [
        (
            b"""Both total nonfarm payroll employment (+57,000) and the
            unemployment rate (4.2 percent) changed little in June.""",
            57_000,
            4.2,
        ),
        (
            b"""Total nonfarm payroll employment edged down by 92,000 in
            February, and the unemployment rate changed little at 4.4
            percent.""",
            -92_000,
            4.4,
        ),
    ],
)
def test_nfp_parser_handles_parenthetical_and_directional_payrolls(
    release: bytes,
    payroll_change: int,
    unemployment_rate: float,
) -> None:
    actual = parse_nfp_actual(release)

    assert actual is not None
    assert actual["payroll_change"] == payroll_change
    assert actual["unemployment_rate"] == unemployment_rate
    assert [row["metric_id"] for row in actual["metrics"]] == [
        "nfp_payroll_change",
        "nfp_unemployment_rate",
    ]
    assert actual["headline_en"]
    assert actual["headline_zh"]


GDP_PAGE = b"""
<html>
  <head><title>GDP (Advance Estimate), Second Quarter 2026</title></head>
  <body>
    <p>Real gross domestic product (GDP) increased at an annual rate of 3.0
    percent in the second quarter of 2026 (April, May, and June), according to
    the advance estimate released today by the U.S. Bureau of Economic
    Analysis. In the first quarter, real GDP increased 2.1 percent.</p>
  </body>
</html>
"""


def test_gdp_page_parser_extracts_vintage_current_and_prior() -> None:
    actual = parse_gdp_actual(GDP_PAGE)

    assert actual is not None
    assert actual["real_gdp_annualized"] == 3.0
    assert actual["prior_real_gdp_annualized"] == 2.1
    assert actual["reference_period"] == "Q2 2026"
    assert actual["vintage"] == "advance"
    assert actual["metrics"] == [
        {
            "metric_id": "gdp_real_annualized",
            "value": 3.0,
            "unit": "percent_annualized",
            "period": "Q2 2026",
        }
    ]
    assert "Q2 2026" in actual["headline_en"]
    assert actual["summary_zh"]


PCE_PAGE = b"""
<html>
  <head><title>Personal Income and Outlays, June 2026</title></head>
  <body>
    <h1>Personal Income and Outlays, June 2026</h1>
    <p>From the preceding month, the PCE price index decreased 0.1 percent.
    Excluding food and energy, the PCE price index increased 0.2 percent.</p>
    <p>From the same month one year ago, the PCE price index increased 2.3
    percent. Excluding food and energy, the PCE price index increased 2.7
    percent.</p>
    <p>Personal income increased $90.0 billion in June.</p>
  </body>
</html>
"""


def test_pce_page_parser_extracts_monthly_and_yearly_inflation() -> None:
    actual = parse_pce_actual(PCE_PAGE)

    assert actual is not None
    assert actual["headline_mom"] == -0.1
    assert actual["core_mom"] == 0.2
    assert actual["headline_yoy"] == 2.3
    assert actual["core_yoy"] == 2.7
    assert actual["reference_period"] == "June 2026"
    assert len(actual["metrics"]) == 4
    assert actual["metrics"][0]["metric_id"] == "pce_headline_mom"
    assert actual["headline_zh"]


CLAIMS_PAGE = b"""
<html>
  <head><title>Unemployment Insurance Weekly Claims - July 23, 2026</title></head>
  <body>
    <p>In the week ending July 18, the advance figure for seasonally adjusted
    initial claims was 217,000, a decrease of 4,000 from the previous week's
    revised level. The previous week's level was revised up by 1,000 from
    220,000 to 221,000. The 4-week moving average was 224,500, a decrease of
    5,000 from the previous week's revised average.</p>
  </body>
</html>
"""


def test_claims_page_parser_extracts_level_change_prior_and_average() -> None:
    actual = parse_claims_actual(CLAIMS_PAGE)

    assert actual is not None
    assert actual["initial_claims"] == 217_000
    assert actual["change"] == -4_000
    assert actual["prior_initial_claims"] == 221_000
    assert actual["four_week_average"] == 224_500
    assert actual["reference_period"] == "July 18, 2026"
    assert [row["metric_id"] for row in actual["metrics"]] == [
        "claims_initial",
        "claims_change",
        "claims_four_week_avg",
    ]
    assert actual["headline_en"] == "Initial claims 217k (-4k)"
    assert actual["headline_zh"]


@pytest.mark.parametrize("parser_name", ["cpi", "ppi", "nfp", "gdp", "pce", "claims"])
def test_named_dispatch_is_fail_closed_and_bilingual(parser_name: str) -> None:
    assert parse_actual(parser_name, b"not an official release") is None
    assert parse_actual("not-a-parser", b"anything") is None
