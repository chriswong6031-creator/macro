"""Tests for collectors/china_trade_detail.py — GACC by-country trade detail (W3 CNH).

Pure/offline surface only — NO network. Both parsers are pinned against the REAL
pages captured from english.customs.gov.cn on 2026-07-27 and committed under
tests/fixtures/china_trade_detail/, so a bulletin reformat breaks a test instead of
quietly writing an empty month.

Covers:
  - the monthly index: UNQUOTED hrefs, the FULL-WIDTH-parenthesis '（2）… by Country
    （Region）…' row label, the year-select OPTION list (the primary current-year
    source — it survives a change-handler rewrite) and the JavaScript map that
    points past years at their own index
  - table (2) in BOTH published shapes: the 10-cell month+cumulative table (June
    2026, 271 partner rows) and the 7-cell year-start table (January 2026, where the
    month IS the cumulative)
  - the '############' Excel-overflow artifact parsed to NaN and COUNTED (never
    dropped, never zero-filled), GACC's '-' nil marker likewise, and continent/bloc
    rows flagged as aggregates
  - keep-FIRST vintage: a re-parse carrying REVISED figures never overwrites the
    first observation (GACC revises silently at the same URL) — and therefore the
    truncation floor, which keeps a partial page from becoming that first vintage
  - the January year-rollover sweep of the prior year's unpublished tail
  - corrupt-store abort, atomic write, empty-key rows dropped and counted

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir) so no tracked
parquet is ever dirtied.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.china_trade_detail as td  # noqa: E402
from lib import config  # noqa: E402

_FIX = Path(__file__).resolve().parent / "fixtures" / "china_trade_detail"
_TS = "2026-07-27T12:00:00+00:00"
_JUN_URL = "http://english.customs.gov.cn/Statics/2d569f57-a86e-4d63-94fb-d3000b039aa7.html"
_JAN_URL = "http://english.customs.gov.cn/Statics/6e9d4074-409f-46a1-883c-3278c5b5b31c.html"


def _fx(name: str) -> str:
    return _FIX.joinpath(name).read_bytes().decode("utf-8")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture(scope="module")
def jun2026():
    return td.parse_by_country(_fx("bycountry_jun2026.html"), _JUN_URL, _TS)


@pytest.fixture(scope="module")
def jan2026():
    return td.parse_by_country(_fx("bycountry_jan2026.html"), _JAN_URL, _TS)


def _by_name(parsed):
    return {r["country_en"]: r for r in parsed["rows"]}


# --------------------------------------------------------------------------- #
# monthly index
# --------------------------------------------------------------------------- #

class TestMonthIndex:
    def test_finds_the_by_country_row_only(self):
        months = td.parse_month_index(_fx("monthly_index.html"))
        # The page ships 19 table types, each with its own Jan..Dec link set. Six
        # months of 2026 are published so far — one row's worth, not nineteen.
        assert len(months) == 6
        assert [m["period"] for m in months] == [
            "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

    def test_june_2026_url_is_the_committed_one(self):
        months = td.parse_month_index(_fx("monthly_index.html"))
        assert months[-1]["url"] == _JUN_URL
        assert months[-1]["label"] == "Jun."

    def test_unquoted_hrefs_are_read(self):
        # The live markup is `<a href=http://…/Statics/<uuid>.html>` with NO quotes.
        html = _fx("monthly_index.html")
        assert "<a href=http://english.customs.gov.cn/Statics/" in html
        assert td.parse_month_index(html)

    def test_full_width_parentheses_in_the_row_label(self):
        # '（2）Imports and Exports by Country （Region） of Origin/Destination' — an
        # ASCII '(2)' or '(Region)' match finds nothing at all.
        html = _fx("monthly_index.html")
        assert "（2）Imports and Exports by Country （Region）" in html
        assert len(td.parse_month_index(html)) == 6

    def test_malformed_nav_links_are_not_month_links(self):
        # The same page carries `http:/statics/report/trade.html` (ONE slash) among
        # its nav links; a naive resolve would emit it as a data URL.
        months = td.parse_month_index(_fx("monthly_index.html"))
        assert all(m["url"].startswith("http://english.customs.gov.cn/Statics/")
                   for m in months)

    def test_year_map_comes_from_the_pages_own_javascript(self):
        year_map = td.parse_year_map(_fx("monthly_index.html"))
        assert set(year_map) == {str(y) for y in range(2018, 2027)}
        assert year_map["2025"].endswith("/monthly2025.html")
        # The CURRENT year is served from the un-suffixed page — the asymmetry a
        # hand-rolled f-string gets wrong every January.
        assert year_map["2026"].endswith("/monthly.html")

    def test_current_year_is_the_sites_notion_not_our_clock(self):
        assert td.current_year(_fx("monthly_index.html")) == "2026"
        assert td.current_year("<html>no year select</html>") == ""

    def test_year_comes_from_the_select_options_not_the_javascript(self):
        """REVIEW F1 — the year must survive a change-handler rewrite.

        The old resolver read ONLY the select's onChange JavaScript. Swapping
        `location.replace` for `window.location.assign` — presentation code, not one
        published figure changed — emptied the year map, stamped every month with an
        EMPTY period, emptied the pending diff and reported a clean 0-row success. A
        silent, permanent death of the plane. The `<option value="YYYY">` list is
        server-rendered DATA and is now the primary source.
        """
        drifted = _fx("monthly_index.html").replace("location.replace(",
                                                    "window.location.assign(")
        assert td.parse_year_map(drifted) == {}          # the JS resolver is now blind
        assert td.select_years(_fx("monthly_index.html"))[0] == "2026"
        assert td.current_year(drifted) == "2026"        # …and the select still answers
        assert [m["period"] for m in td.parse_month_index(drifted)] == [
            "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

    def test_select_max_year_wins_regardless_of_option_order(self):
        html = ('<select id="monthlysel"><option value="2024">2024</option>'
                '<option value="2027">2027</option>'
                '<option value="2025">2025</option></select>')
        assert td.select_years(html) == ["2024", "2027", "2025"]
        assert td.current_year(html) == "2027"

    def test_javascript_is_the_fallback_when_the_options_vanish(self):
        stripped = re.sub(r'(?is)<select[^>]*id="monthlysel".*?</select>', "",
                          _fx("monthly_index.html"))
        assert td.select_years(stripped) == []
        assert td.current_year(stripped) == "2026"       # the JS map still corroborates

    def test_explicit_year_overrides_for_a_backfill_index(self):
        months = td.parse_month_index(_fx("monthly_index.html"), year="2024")
        assert [m["period"] for m in months][:2] == ["2024-01", "2024-02"]

    def test_garbage_page_degrades_to_no_months(self):
        assert td.parse_month_index("") == []
        assert td.parse_month_index("<html><body>nothing</body></html>") == []


# --------------------------------------------------------------------------- #
# table (2)
# --------------------------------------------------------------------------- #

class TestParsePeriod:
    def test_period_from_the_title(self):
        assert td.parse_period(_fx("bycountry_jun2026.html")) == "2026-06"

    def test_missing_title_is_empty_not_a_guess(self):
        assert td.parse_period("<html><body>no title</body></html>") == ""
        assert td.parse_period("<title>no period marker</title>") == ""


class TestParseByCountry:
    def test_row_count_and_period(self, jun2026):
        assert jun2026["period"] == "2026-06"
        assert len(jun2026["rows"]) == 271
        assert jun2026["n_empty_key"] == 0

    def test_header_unit_and_notes_rows_are_not_data(self, jun2026):
        names = {r["country_en"] for r in jun2026["rows"]}
        assert not any(n.startswith("Notes") for n in names)
        assert "Unit:US$1,000" not in names
        assert "Country （Region）" not in names

    def test_united_states_row_exact_numbers(self, jun2026):
        us = _by_name(jun2026)["United States"]
        assert us["total_month_kusd"] == 58066297.0     # commas + &nbsp; stripped
        assert us["total_cum_kusd"] == 289146069.0
        assert us["exports_month_kusd"] == 43463832.0
        assert us["exports_cum_kusd"] == 215919781.0
        assert us["imports_month_kusd"] == 14602465.0
        assert us["imports_cum_kusd"] == 73226289.0
        assert us["pct_total"] == 0.0
        assert us["pct_exports"] == 0.2
        assert us["pct_imports"] == -0.8               # negatives are real
        assert us["is_aggregate"] is False

    def test_total_row_is_flagged_aggregate(self, jun2026):
        total = _by_name(jun2026)["TOTAL"]
        assert total["is_aggregate"] is True
        assert total["total_month_kusd"] == 699151163.0

    def test_continent_and_bloc_rows_are_aggregates(self, jun2026):
        aggregates = {r["country_en"] for r in jun2026["rows"] if r["is_aggregate"]}
        assert aggregates == {
            "TOTAL", "Asia:", "Africa:", "Europe:", "Latin America:",
            "North America:", "Oceania:", "ASEAN", "EU", "APEC", "RCEP", "BRI"}

    def test_overflow_cells_parse_to_nan_and_are_counted(self, jun2026):
        # '############' is Excel column overflow: the figure EXISTS and the page hid
        # it. Zero-filling would delete the five largest cumulative totals in the table.
        assert jun2026["n_overflow"] == 5
        overflowed = _by_name(jun2026)
        for name in ("TOTAL", "Asia:", "APEC", "RCEP", "BRI"):
            assert math.isnan(overflowed[name]["total_cum_kusd"]), name

    def test_overflow_rows_are_kept_not_dropped(self, jun2026):
        # The overflowed cell must not take its whole row with it — every other value
        # on the TOTAL row is intact.
        total = _by_name(jun2026)["TOTAL"]
        assert total["exports_cum_kusd"] == 2125358846.0
        assert total["imports_cum_kusd"] == 1549382917.0

    def test_nil_marker_is_nan_not_zero(self, jun2026):
        antarctica = _by_name(jun2026)["Antarctica"]
        assert math.isnan(antarctica["total_month_kusd"])
        assert math.isnan(antarctica["imports_month_kusd"])

    def test_n_nulls_counts_every_unparseable_value_cell(self, jun2026):
        # 5 overflow cells + 91 '-' nil markers across the June table.
        assert jun2026["n_nulls"] == 96
        assert jun2026["n_nulls"] > jun2026["n_overflow"]
        assert td.count_nulls(jun2026["rows"]) == jun2026["n_nulls"]

    def test_every_row_carries_the_stamps(self, jun2026):
        r = jun2026["rows"][0]
        assert set(r) == set(td._COLUMNS)
        assert r["source_url"] == _JUN_URL
        assert r["first_seen"] == _TS and r["fetched_at"] == _TS
        assert r["backfill"] is False

    def test_empty_country_rows_are_dropped_and_counted(self):
        # country_en is half the dedup key — a keyless row would collapse the whole
        # month into one stored row (W1 F7).
        html = ("<title>x,6.2026</title><table>"
                "<tr><td> </td><td>1</td><td>2</td><td>3</td><td>4</td>"
                "<td>5</td><td>6</td><td>7</td><td>8</td><td>9</td></tr>"
                "<tr><td>Japan</td><td>1</td><td>2</td><td>3</td><td>4</td>"
                "<td>5</td><td>6</td><td>7</td><td>8</td><td>9</td></tr></table>")
        parsed = td.parse_by_country(html)
        assert parsed["n_empty_key"] == 1
        assert [r["country_en"] for r in parsed["rows"]] == ["Japan"]

    def test_garbage_page_degrades(self):
        assert td.parse_by_country("")["rows"] == []
        assert td.parse_by_country("<html>nope</html>")["period"] == ""


class TestJanuarySevenColumnShape:
    """REVIEW F3 (main-session LIVE finding) — the year-start bulletin is 7-column.

    From February on, each of Total/Exports/Imports carries a MONTH and a CUMULATIVE
    column (10 cells per data row). In January the month IS the cumulative, so the
    bulletin prints one column per group and every data row has 7 cells. A hard-coded
    ``len(cells) != 10`` test drops all 271 rows on the floor and files January as a
    parse failure — every year, silently, for the month that anchors the whole
    year-to-date series.
    """

    def test_the_sub_header_declares_the_shape(self):
        assert td.period_columns(_fx("bycountry_jan2026.html")) == 1
        assert td.period_columns(_fx("bycountry_jun2026.html")) == 2
        # an unknown page keeps the historic 10-cell shape rather than guessing
        assert td.period_columns("<html>no table</html>") == 2

    def test_january_rows_and_period(self, jan2026):
        assert jan2026["period"] == "2026-01"
        assert len(jan2026["rows"]) == 271
        assert jan2026["n_empty_key"] == 0

    def test_total_row_exact_numbers(self, jan2026):
        total = _by_name(jan2026)["TOTAL"]
        assert total["total_month_kusd"] == 590758685.0
        assert total["exports_month_kusd"] == 356699626.0
        assert total["imports_month_kusd"] == 234059059.0
        assert total["pct_total"] == 15.7
        assert total["pct_exports"] == 10.0
        assert total["pct_imports"] == 25.6
        assert total["is_aggregate"] is True

    def test_month_is_the_cumulative_in_january(self, jan2026):
        """Not an inference — the bulletin's own arithmetic. A NULL cumulative column
        would read as a coverage gap that does not exist."""
        for name in ("TOTAL", "United States", "Asia:"):
            r = _by_name(jan2026)[name]
            assert r["total_cum_kusd"] == r["total_month_kusd"], name
            assert r["exports_cum_kusd"] == r["exports_month_kusd"], name
            assert r["imports_cum_kusd"] == r["imports_month_kusd"], name

    def test_aggregate_flagging_matches_the_ten_column_shape(self, jan2026):
        aggregates = {r["country_en"] for r in jan2026["rows"] if r["is_aggregate"]}
        assert aggregates == {
            "TOTAL", "Asia:", "Africa:", "Europe:", "Latin America:",
            "North America:", "Oceania:", "ASEAN", "EU", "APEC", "RCEP", "BRI"}

    def test_january_rows_round_trip_the_store(self, store, jan2026):
        assert td.write_rows(jan2026["rows"]) == 271
        stored = td.load_by_country()
        assert set(stored["period"]) == {"2026-01"}
        assert len(stored) == 271

    def test_a_january_page_clears_the_truncation_threshold(self, jan2026):
        # F2's floor applies to this shape too — 271 >= 200, so the month stores.
        assert len(jan2026["rows"]) >= td._MIN_COUNTRY_ROWS


class TestParseValue:
    @pytest.mark.parametrize("raw,expected", [
        ("699,151,163", 699151163.0), ("1,102,975,100 ", 1102975100.0),
        ("21.2", 21.2), ("-0.8", -0.8), ("0", 0.0),
    ])
    def test_numbers(self, raw, expected):
        assert td.parse_value(raw) == expected

    @pytest.mark.parametrize("raw", ["############", "-", "", "   ", None, "n/a"])
    def test_non_numbers_are_nan(self, raw):
        assert math.isnan(td.parse_value(raw))


# --------------------------------------------------------------------------- #
# store — keep-FIRST vintage
# --------------------------------------------------------------------------- #

def _rows(n=3, period="2026-06", fetched=_TS, backfill=False):
    return [{"period": period, "country_en": f"Country{i}", "is_aggregate": False,
             "total_month_kusd": float(i), "total_cum_kusd": float(i),
             "exports_month_kusd": float(i), "exports_cum_kusd": float(i),
             "imports_month_kusd": float(i), "imports_cum_kusd": float(i),
             "pct_total": 1.0, "pct_exports": 1.0, "pct_imports": 1.0,
             "source_url": "u", "backfill": backfill,
             "first_seen": fetched, "fetched_at": fetched}
            for i in range(n)]


class TestStore:
    def test_empty_write_is_zero(self, store):
        assert td.write_rows([]) == 0

    def test_new_rows_land(self, store):
        assert td.write_rows(_rows(3)) == 3
        assert len(td.load_by_country()) == 3

    def test_columns_are_canonical(self, store):
        td.write_rows(_rows(1))
        stored = pd.read_parquet(td._store_path())
        for col in td._COLUMNS:
            assert col in stored.columns, f"missing column: {col}"

    def test_load_returns_schema_when_absent(self, store):
        df = td.load_by_country()
        assert df.empty and list(df.columns) == list(td._COLUMNS)

    def test_revision_never_overwrites_the_first_vintage(self, store):
        td.write_rows(_rows(2))
        revised = _rows(2, fetched="2026-09-01T00:00:00+00:00")
        for r in revised:
            r["total_month_kusd"] = 999.0        # GACC republished with new figures
        assert td.write_rows(revised) == 0       # a revision is not a new row
        stored = td.load_by_country().sort_values("country_en")
        assert list(stored["total_month_kusd"]) == [0.0, 1.0]     # first vintage stands
        assert set(stored["first_seen"]) == {_TS}

    def test_different_periods_coexist(self, store):
        td.write_rows(_rows(2, period="2026-05"))
        assert td.write_rows(_rows(2, period="2026-06")) == 2
        assert set(td.load_by_country()["period"]) == {"2026-05", "2026-06"}

    def test_corrupt_store_aborts_the_append_untouched(self, store):
        td.write_rows(_rows(2))
        corrupt = b"PAR1 this is not a parquet file"
        td._store_path().write_bytes(corrupt)
        assert td.write_rows(_rows(2, period="2026-07")) == 0
        assert td._store_path().read_bytes() == corrupt   # left for manual recovery

    def test_write_is_atomic_no_tmp_residue(self, store):
        assert td.write_rows(_rows(2)) == 2
        leftovers = [p.name for p in td._store_path().parent.iterdir()
                     if p.name != td._store_path().name]
        assert leftovers == []

    def test_stored_periods_is_the_diff_set(self, store):
        assert td.stored_periods() == set()
        td.write_rows(_rows(1, period="2026-06"))
        assert td.stored_periods() == {"2026-06"}

    def test_real_june_table_round_trips(self, store, jun2026):
        assert td.write_rows(jun2026["rows"]) == 271
        stored = td.load_by_country()
        assert len(stored) == 271
        assert set(stored["period"]) == {"2026-06"}
        # NaN survives the parquet round-trip as NaN — never coerced to 0.
        total = stored[stored["country_en"] == "TOTAL"].iloc[0]
        assert math.isnan(total["total_cum_kusd"])


# --------------------------------------------------------------------------- #
# refresh() — diff, degrade, isolate
# --------------------------------------------------------------------------- #

def _wire(monkeypatch, fail=(), index="monthly_index.html", detail="bycountry_jun2026.html"):
    calls: list[str] = []

    def _get(_session, url):
        calls.append(url)
        if url in fail:
            raise IOError("boom")
        return _fx(index) if url == td.INDEX_URL else _fx(detail)

    monkeypatch.setattr(td, "_get", _get)
    return calls


class TestRefresh:
    def test_index_failure_is_a_runtime_error(self, store, monkeypatch):
        _wire(monkeypatch, fail={td.INDEX_URL})
        with pytest.raises(RuntimeError, match="monthly index unreachable"):
            td.refresh()

    def test_first_night_seeds_the_published_months(self, store, monkeypatch):
        calls = _wire(monkeypatch)
        s = td.refresh()
        assert s["n_fetched"] == 6                 # Jan..Jun 2026
        assert s["periods_seen"] == 1              # every fixture page IS June
        assert len([c for c in calls if c != td.INDEX_URL]) == 6
        assert s["n_new"] == 271

    def test_the_pages_own_title_wins_over_the_index_slot(self, store, monkeypatch):
        # Every served detail is the JUNE table, so all six index slots collapse onto
        # 2026-06 rather than being filed under the month the index promised.
        _wire(monkeypatch)
        td.refresh()
        assert set(td.load_by_country()["period"]) == {"2026-06"}

    def test_stored_months_are_never_refetched(self, store, monkeypatch):
        td.write_rows(_rows(1, period="2026-06"))
        calls = _wire(monkeypatch)
        td.refresh()
        fetched = [c for c in calls if c != td.INDEX_URL]
        assert _JUN_URL not in fetched             # June is already on disk
        assert len(fetched) == 5

    def test_a_quiet_night_writes_nothing(self, store, monkeypatch):
        _wire(monkeypatch)
        td.refresh()
        # Every published month is on disk after night one… except that the fixture
        # collapses them onto June, so seed the remaining periods explicitly.
        for p in ("2026-01", "2026-02", "2026-03", "2026-04", "2026-05"):
            td.write_rows(_rows(1, period=p))
        s = td.refresh()
        assert s == {"n_new": 0, "n_fetched": 0, "n_failed": 0, "n_nulls": 0,
                     "periods_seen": 0}

    def test_one_dead_month_does_not_sink_the_rest(self, store, monkeypatch):
        _wire(monkeypatch, fail={_JUN_URL})
        s = td.refresh()
        assert s["n_failed"] == 1 and s["n_fetched"] == 5
        assert s["n_new"] == 271

    def test_an_unusable_page_is_counted_not_stored(self, store, monkeypatch):
        _wire(monkeypatch, detail="monthly_index.html")   # no table (2), no period
        s = td.refresh()
        assert s["n_fetched"] == 6 and s["n_new"] == 0
        assert s["n_failed"] == 6
        assert td.load_by_country().empty

    def test_an_index_without_the_row_is_a_zero_row_night(self, store, monkeypatch):
        monkeypatch.setattr(td, "_get", lambda _s, _u: "<html>no by-country row</html>")
        s = td.refresh()
        assert s == {"n_new": 0, "n_fetched": 0, "n_failed": 1, "n_nulls": 0,
                     "periods_seen": 0}

    def test_wall_clock_guard_stops_the_pull(self, store, monkeypatch):
        _wire(monkeypatch)
        ticks = iter([0.0] * 2 + [td._BUDGET_S + 1.0] * 50)
        monkeypatch.setattr(td, "_clock", lambda: next(ticks))
        s = td.refresh()
        assert s["n_fetched"] <= 2

    def test_a_truncated_month_is_retried_not_frozen(self, store, monkeypatch, caplog):
        """REVIEW F2 — a partial page must never become the permanent first vintage.

        keep-FIRST means the first thing written under a period stays there forever.
        A page that renders 5 of its 271 partner rows (a partial render, a shape drift
        the row matcher half-follows) therefore froze that month at 5 rows for the life
        of the store, with n_new=5 reading as a successful night.
        """
        full = _fx("bycountry_jun2026.html")
        rows = re.findall(r"(?is)<tr[^>]*>.*?</tr>", full)
        # keep the title/unit/header rows + 5 data rows, drop the other 266
        truncated = ("<title>（2）Imports and Exports by Country （Region） of "
                     "Origin/Destination,6.2026</title><table>"
                     + "".join(rows[:9]) + "</table>")
        assert 0 < len(td.parse_by_country(truncated)["rows"]) < td._MIN_COUNTRY_ROWS

        pages = {"truncated": truncated, "full": full}
        state = {"serve": "truncated"}

        def _get(_session, url):
            if url == td.INDEX_URL:
                return _fx("monthly_index.html")
            return pages[state["serve"]]

        monkeypatch.setattr(td, "_get", _get)
        with caplog.at_level("WARNING"):
            night1 = td.refresh()
        assert night1["n_new"] == 0 and night1["n_failed"] == 6
        assert td.load_by_country().empty              # nothing frozen at 5 rows
        assert any("TRUNCATED page" in r.getMessage() for r in caplog.records)
        assert any("only 5 partner rows" in r.getMessage() for r in caplog.records)

        state["serve"] = "full"                         # night 2: the real page is back
        night2 = td.refresh()
        assert night2["n_new"] == 271
        assert len(td.load_by_country()) == 271

    def test_a_year_that_cannot_be_resolved_is_a_loud_failure_not_a_quiet_night(
            self, store, monkeypatch, caplog):
        """REVIEW F1 (second half) — the tripwire behind the year resolver.

        With BOTH the option list and the change-handler gone, every month link stamps
        an empty period, the pending diff is empty and the old code returned the
        all-zero quiet-night sentinel — the collector reporting success while storing
        nothing, forever. n_failed must carry the month count instead.
        """
        blind = re.sub(r'(?is)<select[^>]*id="monthlysel".*?</select>', "",
                       _fx("monthly_index.html")).replace("location.replace(",
                                                          "window.location.assign(")
        calls = []

        def _get(_session, url):
            calls.append(url)
            return blind if url == td.INDEX_URL else _fx("bycountry_jun2026.html")

        monkeypatch.setattr(td, "_get", _get)
        with caplog.at_level("ERROR"):
            s = td.refresh()
        assert s == {"n_new": 0, "n_fetched": 0, "n_failed": 6, "n_nulls": 0,
                     "periods_seen": 0}
        assert calls == [td.INDEX_URL]                  # no month page was even fetched
        assert any("year resolution failed" in r.getMessage() for r in caplog.records)


class TestDecemberRollover:
    """REVIEW F12 — the prior year's tail must not fall off the calendar.

    GACC publishes ~3 weeks in arrears, so when the site rolls monthly.html over to a
    new year in January, LAST year's November and December tables have not been
    published yet — and they never appear on the new index. Without a rollover sweep
    the tape loses two months a year, permanently and silently.
    """

    def _rolled_over_index(self) -> str:
        """The committed 2026 index as it looks the January the site rolls to 2027:
        a new 2027 option/clause pointing at monthly.html, and 2026 demoted to its own
        monthly2026.html — exactly the asymmetry parse_year_map exists to read."""
        html = _fx("monthly_index.html")
        html = html.replace('<option value="2026">2026</option>',
                            '<option value="2027">2027</option>'
                            '<option value="2026">2026</option>')
        html = html.replace(
            'location.replace("http://english.customs.gov.cn/statics/report/monthly.html")',
            'location.replace("http://english.customs.gov.cn/statics/report/monthly2026.html")')
        html = html.replace(
            'if ($("#monthlysel").val() == "2018")',
            'if ($("#monthlysel").val() == "2027") {'
            ' location.replace("http://english.customs.gov.cn/statics/report/monthly.html") }'
            ' if ($("#monthlysel").val() == "2018")')
        assert td.current_year(html) == "2027"
        assert td.parse_year_map(html)["2026"].endswith("/monthly2026.html")
        return html

    def test_prior_year_months_join_the_pending_diff(self, store, monkeypatch):
        td.write_rows(_rows(1, period="2026-06"))       # store's newest year is 2026
        seen: list[str] = []

        def _get(_session, url):
            seen.append(url)
            if url == td.INDEX_URL:
                return self._rolled_over_index()          # the site rolled over
            if url.endswith("monthly2026.html"):
                return _fx("monthly_index.html")        # last year's index, 6 months
            return _fx("bycountry_jun2026.html")

        monkeypatch.setattr(td, "_get", _get)
        s = td.refresh()
        assert "http://english.customs.gov.cn/statics/report/monthly2026.html" in seen
        # 6 new 2027 slots + 5 unstored 2026 months (2026-06 is already on disk)
        assert s["n_fetched"] == 11

    def test_no_sweep_when_the_store_is_already_on_the_current_year(self, store, monkeypatch):
        td.write_rows(_rows(1, period="2026-06"))
        seen: list[str] = []

        def _get(_session, url):
            seen.append(url)
            return _fx("monthly_index.html") if url == td.INDEX_URL \
                else _fx("bycountry_jun2026.html")

        monkeypatch.setattr(td, "_get", _get)
        td.refresh()
        assert not any(u.endswith("monthly2025.html") for u in seen)

    def test_a_dead_prior_year_index_does_not_sink_the_night(self, store, monkeypatch):
        td.write_rows(_rows(1, period="2026-06"))

        def _get(_session, url):
            if url == td.INDEX_URL:
                return self._rolled_over_index()
            if url.endswith("monthly2026.html"):
                raise IOError("boom")
            return _fx("bycountry_jun2026.html")

        monkeypatch.setattr(td, "_get", _get)
        s = td.refresh()
        assert s["n_fetched"] == 6                      # the 2027 months still landed
        assert s["n_new"] == 271

    def test_the_sweep_never_fires_on_a_first_night(self, store, monkeypatch):
        """An EMPTY store is not a rollover — it has no 'prior year' to be behind."""
        seen: list[str] = []

        def _get(_session, url):
            seen.append(url)
            return self._rolled_over_index() if url == td.INDEX_URL \
                else _fx("bycountry_jun2026.html")

        monkeypatch.setattr(td, "_get", _get)
        td.refresh()
        assert not any("monthly2026.html" in u for u in seen)


class TestBackfillIsManualOnly:
    def test_fetch_never_calls_backfill(self, store, monkeypatch):
        # A backfill on the render path would blow the nightly budget; the flag exists
        # so the PIT tape can tell "observed near publication" from "recovered later".
        _wire(monkeypatch)
        called = []
        monkeypatch.setattr(td, "backfill", lambda *a, **k: called.append(a))
        td.ChinaTradeDetailAdapter().fetch()
        assert called == []
        assert not td.load_by_country()["backfill"].any()

    def test_backfill_stamps_the_flag_and_resolves_the_year_index(self, store, monkeypatch):
        seen: list[str] = []

        def _get(_session, url):
            seen.append(url)
            if url.endswith("monthly.html"):
                return _fx("monthly_index.html")
            if url.endswith("monthly2024.html"):
                return _fx("monthly_index.html")
            return _fx("bycountry_jun2026.html")

        monkeypatch.setattr(td, "_get", _get)
        assert td.backfill(["2024"]) == 271
        assert "http://english.customs.gov.cn/statics/report/monthly2024.html" in seen
        stored = td.load_by_country()
        assert stored["backfill"].all()

    def test_unknown_year_is_skipped_not_a_crash(self, store, monkeypatch):
        _wire(monkeypatch)
        assert td.backfill(["1999"]) == 0


# --------------------------------------------------------------------------- #
# adapter contract
# --------------------------------------------------------------------------- #

class TestAdapter:
    def test_sentinel_frame_shape(self, store, monkeypatch):
        _wire(monkeypatch)
        sentinel = td.ChinaTradeDetailAdapter().fetch()["refresh"]
        assert list(sentinel.columns) == list(td._SENTINEL_COLUMNS)
        assert isinstance(sentinel.index, pd.DatetimeIndex)
        assert sentinel.index.tz is None
        assert all(sentinel[c].dtype.kind == "f" for c in sentinel.columns)
        assert not td.ChinaTradeDetailAdapter().validate("refresh", sentinel).empty

    def test_group_prefix_routes_to_the_asia_lane(self):
        assert td.ChinaTradeDetailAdapter.group.startswith("china")
        assert td.ChinaTradeDetailAdapter.stale_after_days == 45   # monthly + ~3wk lag

    def test_adapter_is_registered_and_stays_serial(self):
        from scripts.collect import _CONCURRENT_HOSTS, all_adapters
        assert "china_trade_detail" in all_adapters()
        assert "china_trade_detail" not in _CONCURRENT_HOSTS
