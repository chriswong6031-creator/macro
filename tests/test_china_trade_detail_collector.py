"""Tests for collectors/china_trade_detail.py — GACC by-country trade detail (W3 CNH).

Pure/offline surface only — NO network. Both parsers are pinned against the REAL
pages captured from english.customs.gov.cn on 2026-07-27 and committed under
tests/fixtures/china_trade_detail/, so a bulletin reformat breaks a test instead of
quietly writing an empty month.

Covers:
  - the monthly index: UNQUOTED hrefs, the FULL-WIDTH-parenthesis '（2）… by Country
    （Region）…' row label, and the year-select JavaScript that maps past years to
    their own index (the current year is the un-suffixed monthly.html)
  - table (2): 271 partner rows for June 2026, the '############' Excel-overflow
    artifact parsed to NaN and COUNTED (never dropped, never zero-filled), GACC's
    '-' nil marker likewise, and continent/bloc rows flagged as aggregates
  - keep-FIRST vintage: a re-parse carrying REVISED figures never overwrites the
    first observation (GACC revises silently at the same URL)
  - corrupt-store abort, atomic write, empty-key rows dropped and counted

Storage is redirected to tmp_path (monkeypatched lib.config.data_dir) so no tracked
parquet is ever dirtied.
"""
from __future__ import annotations

import math
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


def _fx(name: str) -> str:
    return _FIX.joinpath(name).read_bytes().decode("utf-8")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture(scope="module")
def jun2026():
    return td.parse_by_country(_fx("bycountry_jun2026.html"), _JUN_URL, _TS)


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
