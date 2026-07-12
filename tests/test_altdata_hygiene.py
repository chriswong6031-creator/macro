"""Unit tests for altdata hygiene sweep (PR-C).

Covers:
  - add() guard fix: upgrade channels displace base exactly once; base-fires-twice does not overwrite
  - DPI z fallback: <20 distinct dates => basis='threshold', z=None
  - relative app velocity: delta/prior with floor=1000
  - 13F time window: old filings filtered out
  - offexchange stale flag: fired when latest date > stale_bdays business days ago
  - pagination: _get_paged() loops until empty or cap, dedup preserved

No network; all fixtures are in-memory.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from engine import altdata, altdata_models as models
from collectors import quiver


# --------------------------------------------------------------------------- helpers
def _now_ts() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))


# ===========================================================================
# B7: add() guard — upgrade channels + base-fires-twice regression
# ===========================================================================
class TestAddGuard:
    """Regression tests for channel_records().add() guard fix."""

    def _run(self, signal_dict):
        """Run channel_records with minimal empty signal blocks."""
        base = {
            "political": {"buys": [], "sells": []},
            "gov_contracts": [], "gov_grants": [], "lobbying": [],
            "insiders": {"buys": []}, "offexchange": [], "inst_13f": {"adds": []},
            "trump": [], "cnbc": [], "fda": [], "material_8k": [],
            "app_ratings": [], "patents": [], "retail": [], "hf": [],
            "unusual_options": [], "analyst": [], "insider_mspr": [],
            "earnings": [], "news_sentiment": [], "clinical": [], "github": [],
            "congress_holdings": {}, "corporate_donors": [], "special_situations": [],
        }
        base.update(signal_dict)
        return models.channel_records(base)

    def test_upgrade_displaces_base(self):
        """Congress cluster (>=3 members) must displace congress_buy on the same ticker."""
        signals = {
            "political": {"buys": [
                {"ticker": "AAA", "net": 3, "members": 3},  # fires cluster
            ]},
        }
        recs = self._run(signals)
        assert "AAA" in recs
        channels = set(recs["AAA"]["channels"])
        assert "congress_cluster" in channels
        assert "congress_buy" not in channels   # displaced

    def test_base_fires_twice_then_upgrade_wins(self):
        """Base fires twice (two sources), then upgrade fires.
        Upgrade must win; neither base instance should survive."""
        # Simulate: first a single congress buy (members=1 => base),
        # then the same ticker appears as cluster (members=3 => upgrade).
        # In channel_records the political buys list is iterated once;
        # to simulate "two base sources" we use two distinct signal blocks.
        # Use insider_buy (base) vs insider_cluster (upgrade) which have the
        # same `drops` pattern:
        #   add("IBUYER", "insider_buy", ...) called twice via two rows
        #   add("IBUYER", "insider_cluster", ..., drops=("insider_buy",)) called once
        signals = {
            "insiders": {"buys": [
                # Two rows firing the base channel
                {"ticker": "IBUYER", "net_usd": 5_000, "buyers": 1},
                {"ticker": "IBUYER", "net_usd": 8_000, "buyers": 2},  # second base fire
                # Third row fires the upgrade
                {"ticker": "IBUYER", "net_usd": 50_000, "buyers": 3},
            ]},
        }
        recs = self._run(signals)
        assert "IBUYER" in recs
        channels = set(recs["IBUYER"]["channels"])
        assert "insider_cluster" in channels, f"got channels: {channels}"
        assert "insider_buy" not in channels, "base should be displaced by upgrade"

    def test_base_fires_twice_no_upgrade_first_wins(self):
        """If base fires twice and no upgrade follows, first detail is preserved
        (second base call is a no-op — first-seen semantics)."""
        # CNBC picks: add(tk, "cnbc_pick", trader_name) — no drops
        # Two rows for same ticker: only the first detail should survive
        signals = {
            "cnbc": [
                {"Ticker": "CNBC1", "Direction": "buy", "Traders": "Trader A"},
                {"Ticker": "CNBC1", "Direction": "buy", "Traders": "Trader B"},
            ],
        }
        recs = self._run(signals)
        assert "CNBC1" in recs
        detail = recs["CNBC1"]["channel_detail"].get("cnbc_pick")
        # first-seen semantics: first call's detail wins
        assert detail == "Trader A", f"expected Trader A, got {detail!r}"

    def test_upgrade_without_prior_base_still_fires(self):
        """An upgrade channel (drops non-empty) must fire even if base was never set."""
        signals = {
            "insiders": {"buys": [
                # Only the cluster row — no prior base row
                {"ticker": "CLUSTONLY", "net_usd": 50_000, "buyers": 3},
            ]},
        }
        recs = self._run(signals)
        assert "CLUSTONLY" in recs
        channels = set(recs["CLUSTONLY"]["channels"])
        assert "insider_cluster" in channels
        assert "insider_buy" not in channels


# ===========================================================================
# B6: DPI z fallback — >=20 distinct dates required
# ===========================================================================
class TestDpiZFallback:
    """DPI z-score requires >=20 distinct dates; fewer => basis='threshold', z=None."""

    def _offexchange_df(self, n_dates: int, dpi_val: float = 0.30) -> pd.DataFrame:
        dates = pd.date_range("2025-01-01", periods=n_dates, freq="B")
        return pd.DataFrame({
            "Ticker": ["AAA"] * n_dates,
            "Date": dates.strftime("%Y-%m-%d"),
            "DPI": [dpi_val] * n_dates,
        })

    def test_fewer_than_20_dates_gives_threshold_basis(self, monkeypatch):
        df = self._offexchange_df(n_dates=10)
        monkeypatch.setattr(models, "_read", lambda ds: df if ds == "offexchange" else None)
        result = models._dpi_z_lookup()
        assert "AAA" in result
        assert result["AAA"]["basis"] == "threshold"
        assert result["AAA"]["z"] is None

    def test_exactly_20_dates_gives_z_score_basis(self, monkeypatch):
        # Use varied DPI values so std > 0
        n = 20
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        dpi_vals = [0.30 + 0.01 * i for i in range(n)]  # increasing to give variance
        df = pd.DataFrame({
            "Ticker": ["BBB"] * n,
            "Date": dates.strftime("%Y-%m-%d"),
            "DPI": dpi_vals,
        })
        monkeypatch.setattr(models, "_read", lambda ds: df if ds == "offexchange" else None)
        result = models._dpi_z_lookup()
        assert "BBB" in result
        assert result["BBB"]["basis"] == "z_score"
        assert result["BBB"]["z"] is not None
        # Sanity: z uses ddof=1, so std is slightly larger → |z| slightly smaller than ddof=0
        import numpy as np
        vals = dpi_vals
        mu = float(pd.Series(vals).mean())
        sd_ddof1 = float(pd.Series(vals).std(ddof=1))
        expected_z = round((vals[-1] - mu) / sd_ddof1, 2)
        assert result["BBB"]["z"] == pytest.approx(expected_z, abs=0.01)

    def test_more_than_20_dates_uses_ddof1(self, monkeypatch):
        """Verify ddof=1 is used (not ddof=0) for z computation with >=20 dates."""
        n = 25
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        dpi_vals = [0.40 - 0.005 * i for i in range(n)]
        df = pd.DataFrame({
            "Ticker": ["CCC"] * n,
            "Date": dates.strftime("%Y-%m-%d"),
            "DPI": dpi_vals,
        })
        monkeypatch.setattr(models, "_read", lambda ds: df if ds == "offexchange" else None)
        result = models._dpi_z_lookup()
        assert "CCC" in result
        assert result["CCC"]["basis"] == "z_score"
        # ddof=1 std is larger than ddof=0 std, so |z| is smaller with ddof=1
        s = pd.Series(dpi_vals)
        mu = float(s.mean())
        sd1 = float(s.std(ddof=1))
        sd0 = float(s.std(ddof=0))
        latest = dpi_vals[-1]
        z1 = round((latest - mu) / sd1, 2)
        z0 = round((latest - mu) / sd0, 2)
        assert result["CCC"]["z"] == pytest.approx(z1, abs=0.01)
        assert result["CCC"]["z"] != pytest.approx(z0, abs=0.001)  # they differ


# ===========================================================================
# B8: relative app velocity
# ===========================================================================
class TestAppVelocity:
    """app_ratings_momentum now uses relative velocity (delta/prior) with floor=1000."""

    def _make_df(self, t1_count, t2_count, ticker="AAPL"):
        rows = [
            {"Ticker": ticker, "App": "MyApp", "Rating": 4.5, "Count": t1_count, "Time": "2026-06-01"},
            {"Ticker": ticker, "App": "MyApp", "Rating": 4.5, "Count": t2_count, "Time": "2026-07-01"},
        ]
        return pd.DataFrame(rows)

    def test_relative_velocity_computed(self, monkeypatch):
        """With 10000 prior and 12000 current: relative vel = (12000-10000)/10000 = 0.2."""
        df = self._make_df(t1_count=10000, t2_count=12000)
        monkeypatch.setattr(models, "_read", lambda ds: df if ds == "appratings" else None)
        rows = models.app_ratings_momentum(top=5)
        assert rows
        r = rows[0]
        assert r["review_velocity"] is not None
        assert r["review_velocity"] == pytest.approx(0.2, abs=0.001)

    def test_small_prior_returns_none(self, monkeypatch):
        """Prior count <1000 => no velocity (floor prevents tiny-denominator blowup)."""
        df = self._make_df(t1_count=500, t2_count=600)
        monkeypatch.setattr(models, "_read", lambda ds: df if ds == "appratings" else None)
        rows = models.app_ratings_momentum(top=5)
        assert rows
        r = rows[0]
        assert r["review_velocity"] is None

    def test_mega_platform_bias_eliminated(self, monkeypatch):
        """Large-platform delta/prior should equal small-platform delta/prior
        when growth rate is the same (relative = scale-invariant)."""
        df = pd.DataFrame([
            {"Ticker": "BIG", "App": "Big App", "Rating": 4.0, "Count": 1_000_000, "Time": "2026-06-01"},
            {"Ticker": "BIG", "App": "Big App", "Rating": 4.0, "Count": 1_100_000, "Time": "2026-07-01"},  # 10% growth
            {"Ticker": "SML", "App": "Small App", "Rating": 4.0, "Count": 10_000, "Time": "2026-06-01"},
            {"Ticker": "SML", "App": "Small App", "Rating": 4.0, "Count": 11_000, "Time": "2026-07-01"},   # 10% growth
        ])
        monkeypatch.setattr(models, "_read", lambda ds: df if ds == "appratings" else None)
        rows = models.app_ratings_momentum(top=10)
        by_tk = {r["ticker"]: r for r in rows}
        big_vel = by_tk["BIG"]["review_velocity"]
        sml_vel = by_tk["SML"]["review_velocity"]
        assert big_vel is not None and sml_vel is not None
        assert big_vel == pytest.approx(sml_vel, abs=0.001)  # same 10% growth => same relative vel


# ===========================================================================
# C10: 13F time window
# ===========================================================================
class TestInst13FWindow:
    """inst_13f_changes must filter to filings within window_days."""

    def _make_df(self):
        now = _now_ts()
        return pd.DataFrame([
            # Recent filing — within 120 days
            {"Ticker": "NVDA", "Fund": "Citadel", "ReportPeriod": "2026-03-31",
             "Date": (now - pd.Timedelta(days=30)).strftime("%Y-%m-%d"),
             "Change": 1_000_000, "Change_Share": 5000},
            # Old filing — more than 120 days ago
            {"Ticker": "META", "Fund": "Scion", "ReportPeriod": "2025-09-30",
             "Date": (now - pd.Timedelta(days=200)).strftime("%Y-%m-%d"),
             "Change": 2_000_000, "Change_Share": 3000},
        ])

    def test_old_filing_excluded(self, monkeypatch):
        df = self._make_df()
        monkeypatch.setattr(altdata, "_read", lambda ds: df if ds == "sec13f_changes" else None)
        result = altdata.inst_13f_changes(window_days=120)
        tickers = {r["ticker"] for r in result["adds"]}
        assert "NVDA" in tickers, "recent filing should be included"
        assert "META" not in tickers, "old filing (>120d) should be excluded"

    def test_no_date_column_passes_through(self, monkeypatch):
        """When Date column has no valid values, rows should still pass through
        (the filter uses `isna() | in-window`, so NaT rows survive)."""
        df = pd.DataFrame([
            {"Ticker": "GOOG", "Fund": "Bridgewater", "ReportPeriod": "2026-03-31",
             "Date": None, "Change": 500_000, "Change_Share": 1000},
        ])
        monkeypatch.setattr(altdata, "_read", lambda ds: df if ds == "sec13f_changes" else None)
        result = altdata.inst_13f_changes(window_days=120)
        tickers = {r["ticker"] for r in result["adds"]}
        assert "GOOG" in tickers, "rows with no date should survive the filter"


# ===========================================================================
# C12: offexchange stale flag
# ===========================================================================
class TestOffexchangeStaleFlag:
    """offexchange_flow must set stale=True when latest date >stale_bdays business days old."""

    def _make_df(self, days_ago: int) -> pd.DataFrame:
        date = (_now_ts() - pd.Timedelta(days=days_ago)).strftime("%Y-%m-%d")
        return pd.DataFrame([
            {"Ticker": "SPY", "Date": date, "OTC_Short": 1000, "OTC_Total": 5000, "DPI": 0.35},
            {"Ticker": "QQQ", "Date": date, "OTC_Short": 800, "OTC_Total": 4000, "DPI": 0.45},
        ])

    def test_fresh_data_not_stale(self, monkeypatch):
        """Data 3 calendar days old (well within 10 bday window) => stale=False."""
        df = self._make_df(days_ago=3)
        monkeypatch.setattr(altdata, "_read", lambda ds: df if ds == "offexchange" else None)
        rows = altdata.offexchange_flow(stale_bdays=10)
        assert rows
        assert all(not r["stale"] for r in rows), "recent data should not be stale"

    def test_old_data_flagged_stale(self, monkeypatch):
        """Data 20 calendar days old (>10 business days) => stale=True."""
        df = self._make_df(days_ago=20)
        monkeypatch.setattr(altdata, "_read", lambda ds: df if ds == "offexchange" else None)
        rows = altdata.offexchange_flow(stale_bdays=10)
        assert rows
        assert all(r["stale"] for r in rows), "old data should be stale"

    def test_stale_key_always_present(self, monkeypatch):
        """The 'stale' key must be present in every row regardless of freshness."""
        df = self._make_df(days_ago=1)
        monkeypatch.setattr(altdata, "_read", lambda ds: df if ds == "offexchange" else None)
        rows = altdata.offexchange_flow()
        assert rows
        for r in rows:
            assert "stale" in r, f"stale key missing from row: {r}"


# ===========================================================================
# Collectors: pagination
# ===========================================================================
class TestPaginatedFetch:
    """_get_paged() must loop pages until empty response or cap reached."""

    class _PagedAdapter(quiver.QuiverAdapter):
        name = "quiver_test_paged"; dataset = "test_paged"
        endpoint = "/beta/bulk/test"
        _paginated = True
        query = {"page": 1, "page_size": 2}
        key_cols = ("id",)

    def test_multi_page_collects_all_rows(self, tmp_path, monkeypatch):
        """Three pages of 2 rows each should yield 6 rows in the store."""
        monkeypatch.setattr(quiver.config, "data_dir", lambda: tmp_path)
        adapter = self._PagedAdapter()
        adapter.api_key = "fake_key"

        page_data = {
            1: [{"id": "a1"}, {"id": "a2"}],
            2: [{"id": "b1"}, {"id": "b2"}],
            3: [{"id": "c1"}, {"id": "c2"}],
            4: [],  # empty stops loop
        }

        def _fake_get(endpoint, params=None):
            p = int((params or {}).get("page", 1))
            return page_data.get(p, [])

        monkeypatch.setattr(adapter, "_get", _fake_get)
        all_rows = adapter._get_paged()
        assert len(all_rows) == 6

    def test_cap_limits_pages(self, tmp_path, monkeypatch):
        """Even if server keeps returning data, cap (_page_cap=5) stops the loop."""
        monkeypatch.setattr(quiver.config, "data_dir", lambda: tmp_path)
        adapter = self._PagedAdapter()
        adapter.api_key = "fake_key"
        adapter._page_cap = 3  # limit to 3 pages for this test

        def _fake_get(endpoint, params=None):
            # always returns full pages — never empty
            p = int((params or {}).get("page", 1))
            return [{"id": f"p{p}r{i}"} for i in range(2)]

        monkeypatch.setattr(adapter, "_get", _fake_get)
        all_rows = adapter._get_paged()
        assert len(all_rows) == 6  # 3 pages × 2 rows

    def test_dedup_preserved_across_pages(self, tmp_path, monkeypatch):
        """Duplicate keys across pages must be deduped by _merge (keep='first')."""
        monkeypatch.setattr(quiver.config, "data_dir", lambda: tmp_path)
        adapter = self._PagedAdapter()
        adapter.api_key = "fake_key"

        # Page 2 returns a duplicate key from page 1
        page_data = {
            1: [{"id": "x1", "val": "original"}, {"id": "x2", "val": "original"}],
            2: [{"id": "x1", "val": "duplicate"}],  # same key as page 1 row
            3: [],
        }

        def _fake_get(endpoint, params=None):
            p = int((params or {}).get("page", 1))
            return page_data.get(p, [])

        monkeypatch.setattr(adapter, "_get", _fake_get)
        # Simulate a full fetch
        rows = adapter._get_paged()
        assert len(rows) == 3  # 2 unique + 1 duplicate
        df = pd.DataFrame(rows)
        added, total = adapter._merge(df)
        final = pd.read_parquet(adapter._table_path())
        # Only 2 unique ids
        assert len(final) == 2
        # First-seen wins
        x1 = final[final["id"] == "x1"].iloc[0]
        assert x1["val"] == "original"


# ===========================================================================
# Tombstone: dead adapters return empty dict
# ===========================================================================
class TestTombstonedAdapters:
    """Tombstoned adapters (Twitter, Spacs, Flights) must return {} from fetch()."""

    def _adapter(self, cls, tmp_path, monkeypatch):
        monkeypatch.setattr(quiver.config, "data_dir", lambda: tmp_path)
        a = cls()
        a.api_key = "fake_key"  # set so we don't fail on "not set"
        return a

    def test_twitter_fetch_returns_empty(self, tmp_path, monkeypatch):
        a = self._adapter(quiver.TwitterAdapter, tmp_path, monkeypatch)
        result = a.fetch()
        assert result == {}, f"expected empty dict, got {result!r}"

    def test_spacs_fetch_returns_empty(self, tmp_path, monkeypatch):
        a = self._adapter(quiver.SpacsAdapter, tmp_path, monkeypatch)
        result = a.fetch()
        assert result == {}, f"expected empty dict, got {result!r}"

    def test_flights_fetch_returns_empty(self, tmp_path, monkeypatch):
        a = self._adapter(quiver.FlightsAdapter, tmp_path, monkeypatch)
        result = a.fetch()
        assert result == {}, f"expected empty dict, got {result!r}"
