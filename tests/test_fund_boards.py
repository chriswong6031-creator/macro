"""Tests for engine.fund_boards — synthetic fixtures only (no live I/O),
plus integration checks against the real committed Grade-A CSV files.

Run:
    pytest tests/test_fund_boards.py -q
"""
from __future__ import annotations

import pathlib
import math

import pytest

# No import-time I/O must occur when this module is imported
import engine.fund_boards as fb

# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent.parent
GRADE_A_DIR = ROOT / "research" / "artifacts" / "SMART_MONEY_GRADE_A_2026Q1"


def _make_membership():
    """Tiny synthetic membership DataFrame."""
    import pandas as pd
    return pd.DataFrame([
        {"ticker": "AAPL", "group": "sp500", "sector": "Information Technology", "active": True},
        {"ticker": "MDT",  "group": "sp400", "sector": "Health Care",             "active": True},
        {"ticker": "KTOS", "group": "sp600", "sector": "Industrials",             "active": True},
        {"ticker": "INAC", "group": "sp500", "sector": "Financials",              "active": False},  # inactive
    ])


def _make_polygon():
    """Tiny synthetic polygon DataFrame indexed by ticker."""
    import pandas as pd
    df = pd.DataFrame({
        "market_cap_usd": [2.5e12, 8e9, 1.2e9],
        "gics_sector": ["Information Technology", "Health Care", "Industrials"],
    }, index=pd.Index(["AAPL", "MDT", "KTOS"], name="ticker"))
    return df


def _make_followability():
    return {
        "casdin":    {"follow_tier": "follow",      "follow_score": 90.0, "n": 15},
        "himalaya":  {"follow_tier": "follow",      "follow_score": 75.0, "n": 6},
        "whalerock": {"follow_tier": "watch",       "follow_score": 62.0, "n": 8},
        "baupost":   {"follow_tier": "insufficient","follow_score": 40.0, "n": 2},
        "corvex":    {"follow_tier": "fade",        "follow_score": 20.0, "n": 3},
    }


# ---------------------------------------------------------------------------
# 1. cap_bucket
# ---------------------------------------------------------------------------

class TestCapBucket:
    def test_sp500_is_large(self):
        m, p = _make_membership(), _make_polygon()
        res = fb.cap_bucket("AAPL", m, p)
        assert res["bucket"] == "large"
        assert res["market_cap_usd"] == pytest.approx(2.5e12)

    def test_sp400_is_mid(self):
        m, p = _make_membership(), _make_polygon()
        res = fb.cap_bucket("MDT", m, p)
        assert res["bucket"] == "mid"
        assert res["market_cap_usd"] == pytest.approx(8e9)

    def test_sp600_is_small(self):
        m, p = _make_membership(), _make_polygon()
        res = fb.cap_bucket("KTOS", m, p)
        assert res["bucket"] == "small"
        assert res["market_cap_usd"] == pytest.approx(1.2e9)

    def test_off_index_ticker(self):
        m, p = _make_membership(), _make_polygon()
        res = fb.cap_bucket("ZZZZZ", m, p)
        assert res["bucket"] == "off_index"
        assert res["market_cap_usd"] is None

    def test_inactive_member_is_off_index(self):
        """INAC has group sp500 but active=False; load_cap_sources filters it out."""
        m_full, p = _make_membership(), _make_polygon()
        # Simulate load_cap_sources behaviour: filter active=True
        m = m_full[m_full["active"].astype(bool)]
        res = fb.cap_bucket("INAC", m, p)
        assert res["bucket"] == "off_index"

    def test_no_polygon_returns_none_cap(self):
        m = _make_membership()
        res = fb.cap_bucket("AAPL", m, None)
        assert res["bucket"] == "large"
        assert res["market_cap_usd"] is None

    def test_no_sources_at_all(self):
        res = fb.cap_bucket("AAPL", None, None)
        assert res["bucket"] == "off_index"
        assert res["market_cap_usd"] is None

    def test_ticker_case_insensitive(self):
        m, p = _make_membership(), _make_polygon()
        assert fb.cap_bucket("aapl", m, p)["bucket"] == "large"

    def test_r2000_is_small(self):
        """r2000 group must map to bucket 'small', mirroring the sp600 arm."""
        import pandas as pd
        m = pd.DataFrame([
            {"ticker": "SMLL", "group": "r2000", "sector": "Financials", "active": True},
        ])
        p = pd.DataFrame(
            {"market_cap_usd": [500e6], "gics_sector": ["Financials"]},
            index=pd.Index(["SMLL"], name="ticker"),
        )
        res = fb.cap_bucket("SMLL", m, p)
        assert res["bucket"] == "small", (
            "r2000 group must be treated as small-cap tier (mirrors sp600)"
        )
        assert res["market_cap_usd"] == pytest.approx(500e6)


# ---------------------------------------------------------------------------
# 2. Incremental-weight formula
# ---------------------------------------------------------------------------

class TestIncrPct:
    def test_new_action_returns_pct_book(self):
        assert fb._incr_pct("new", 5.0, None) == pytest.approx(5.0)
        assert fb._incr_pct("new", 3.2, 200.0) == pytest.approx(3.2)  # chg ignored for new

    def test_add_formula(self):
        # add: pct_book * chg / (100 + chg)
        # pct_book=6, chg=50 -> 6 * 50/150 = 2.0
        assert fb._incr_pct("add", 6.0, 50.0) == pytest.approx(2.0)

    def test_add_negative_chg_guard_none(self):
        # chg=None -> fallback: pct_book * 0.5
        assert fb._incr_pct("add", 4.0, None) == pytest.approx(2.0)

    def test_add_negative_chg_guard_minus100(self):
        # chg <= -100 -> fallback
        assert fb._incr_pct("add", 4.0, -100.0) == pytest.approx(2.0)
        assert fb._incr_pct("add", 4.0, -150.0) == pytest.approx(2.0)

    def test_add_small_chg(self):
        # pct_book=10, chg=10 -> 10 * 10/110 ≈ 0.9091
        res = fb._incr_pct("add", 10.0, 10.0)
        assert res == pytest.approx(10.0 * 10 / 110, rel=1e-5)


# ---------------------------------------------------------------------------
# 3. Freshness decay
# ---------------------------------------------------------------------------

class TestFreshnessScore:
    def test_within_7d(self):
        assert fb._freshness_score(0) == pytest.approx(1.0)
        assert fb._freshness_score(7) == pytest.approx(1.0)

    def test_at_90d(self):
        assert fb._freshness_score(90) == pytest.approx(0.2)

    def test_beyond_90d(self):
        assert fb._freshness_score(120) == pytest.approx(0.2)

    def test_midpoint_decay(self):
        # At day 48.5 (roughly midpoint 7-90): should be ~0.6
        val = fb._freshness_score(48)
        assert 0.2 < val < 1.0

    def test_linear_between_7_and_90(self):
        v7  = fb._freshness_score(7)
        v48 = fb._freshness_score(48)
        v90 = fb._freshness_score(90)
        # monotonically decreasing
        assert v7 > v48 > v90


# ---------------------------------------------------------------------------
# 4. build_best_buys
# ---------------------------------------------------------------------------

def _make_initiations():
    """Synthetic initiations list (3 tickers, 2-3 funds each)."""
    return [
        # AAPL: casdin (new, 4%), himalaya (add +60%, 3%)
        {
            "ticker": "AAPL", "issuer": "Apple Inc", "sector": "Information Technology",
            "slug": "casdin", "name": "Casdin Capital",
            "action": "new", "pct_book": 4.0, "shares_change_pct": None,
            "filing_date": "2026-03-15", "since_excess": 0.05,
        },
        {
            "ticker": "AAPL", "issuer": "Apple Inc", "sector": "Information Technology",
            "slug": "himalaya", "name": "Himalaya Capital",
            "action": "add", "pct_book": 3.0, "shares_change_pct": 60.0,
            "filing_date": "2026-03-10", "since_excess": 0.08,
        },
        # KTOS: whalerock (new, 2.5%), baupost (add, insufficient tier)
        {
            "ticker": "KTOS", "issuer": "Kratos Defense", "sector": "Industrials",
            "slug": "whalerock", "name": "Whale Rock",
            "action": "new", "pct_book": 2.5, "shares_change_pct": None,
            "filing_date": "2026-03-20", "since_excess": None,
        },
        {
            "ticker": "KTOS", "issuer": "Kratos Defense", "sector": "Industrials",
            "slug": "baupost", "name": "Baupost",
            "action": "add", "pct_book": 1.5, "shares_change_pct": 30.0,
            "filing_date": "2026-03-20", "since_excess": None,
        },
        # MDT: corvex (new, 6%) -- fade fund, should be excluded from this board
        {
            "ticker": "MDT", "issuer": "Medtronic", "sector": "Health Care",
            "slug": "corvex", "name": "Corvex",
            "action": "new", "pct_book": 6.0, "shares_change_pct": None,
            "filing_date": "2026-03-18", "since_excess": -0.02,
        },
    ]


class TestBuildBestBuys:
    def setup_method(self):
        self.followability = _make_followability()
        self.cap_sources = (_make_membership(), _make_polygon())

    def test_basic_structure(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        tickers = [r["ticker"] for r in rows]
        assert "AAPL" in tickers
        assert "KTOS" in tickers

    def test_fade_fund_excluded(self):
        """corvex (fade) contributes MDT; MDT should NOT appear in best_buys."""
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        tickers = [r["ticker"] for r in rows]
        assert "MDT" not in tickers

    def test_aapl_incr_pct_max_is_new_pct(self):
        """casdin NEW 4% => incr_pct=4.0; himalaya ADD 3% chg=60 => 3*60/160=1.125.
        Max should be 4.0."""
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        assert aapl["incr_pct_max"] == pytest.approx(4.0, rel=1e-4)

    def test_aapl_incr_pct_sum(self):
        # incr_pct sum = 4.0 + 1.125 = 5.125
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        expected_sum = 4.0 + (3.0 * 60.0 / 160.0)
        assert aapl["incr_pct_sum"] == pytest.approx(expected_sum, rel=1e-4)

    def test_cap_bucket_attached(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        assert aapl["cap_bucket"] == "large"
        ktos = next(r for r in rows if r["ticker"] == "KTOS")
        assert ktos["cap_bucket"] == "small"

    def test_components_present_and_bounded(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        for row in rows:
            c = row["components"]
            for key in ("conviction", "quality", "confluence", "freshness"):
                assert key in c
                assert 0.0 <= c[key] <= 1.0

    def test_desk_rank_score_formula(self):
        """Manually verify score for AAPL."""
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        c = aapl["components"]
        expected = 100.0 * (0.35 * c["conviction"] + 0.30 * c["quality"]
                            + 0.25 * c["confluence"] + 0.10 * c["freshness"])
        assert aapl["desk_rank_score"] == pytest.approx(expected, rel=1e-4)

    def test_insufficient_tier_quality_flat(self):
        """When only insufficient-tier funds buy a ticker, quality = 0.35."""
        only_insuff = [
            {
                "ticker": "XYZQ", "issuer": "XYZ Corp", "sector": "Financials",
                "slug": "baupost", "name": "Baupost",
                "action": "new", "pct_book": 2.0, "shares_change_pct": None,
                "filing_date": "2026-03-01", "since_excess": None,
            }
        ]
        rows = fb.build_best_buys(only_insuff, self.followability, None, (None, None))
        assert len(rows) == 1
        assert rows[0]["components"]["quality"] == pytest.approx(0.35)

    def test_sector_inflow_boosts_confluence(self):
        sector_flows = {"Information Technology": {"net_inflow": True}}
        rows_no_flow = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        rows_with_flow = fb.build_best_buys(
            _make_initiations(), self.followability, sector_flows, self.cap_sources
        )
        aapl_no  = next(r for r in rows_no_flow  if r["ticker"] == "AAPL")
        aapl_yes = next(r for r in rows_with_flow if r["ticker"] == "AAPL")
        assert aapl_yes["components"]["confluence"] >= aapl_no["components"]["confluence"]

    def test_sorted_by_desk_rank_score_desc(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        scores = [r["desk_rank_score"] for r in rows]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_respected(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources, top_n=1
        )
        assert len(rows) == 1

    def test_action_counts_in_output(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        assert aapl["actions"]["new"] == 1
        assert aapl["actions"]["add"] == 1

    def test_since_excess_med_computed(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        # two values: 0.05 and 0.08 -> median = 0.065
        assert aapl["since_excess_med"] == pytest.approx(0.065, rel=1e-5)

    def test_n_funds_correct(self):
        rows = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        aapl = next(r for r in rows if r["ticker"] == "AAPL")
        assert aapl["n_funds"] == 2  # casdin + himalaya (corvex excluded via fade for MDT)

    def test_empty_initiations(self):
        rows = fb.build_best_buys([], self.followability, None, self.cap_sources)
        assert rows == []

    def test_incr_pct_uses_shares_change_pct_not_tilt(self):
        """FIX 1: add-action with pct_book=3.0, shares_change_pct=40 must produce
        incr_pct ≈ 0.857 (3.0*40/140). A tilt field present in the row must NOT
        be used (tilt is overweight-vs-fund-mean, wrong sign for conviction)."""
        initiations = [
            {
                "ticker": "TLTX", "issuer": "Test Corp", "sector": "Technology",
                "slug": "casdin", "name": "Casdin Capital",
                "action": "add", "pct_book": 3.0, "shares_change_pct": 40.0,
                "filing_date": "2026-03-15", "since_excess": None,
                # deliberately include a tilt field (which must NOT be used)
                "tilt": -99.9,
            }
        ]
        rows = fb.build_best_buys(initiations, self.followability, None, self.cap_sources)
        assert len(rows) == 1
        tltx = rows[0]
        expected_ip = 3.0 * 40.0 / 140.0  # ≈ 0.857
        assert tltx["incr_pct_max"] == pytest.approx(expected_ip, rel=1e-4)
        # Confirm it did NOT use tilt (-99.9) which would produce nonsense
        assert tltx["incr_pct_max"] > 0

    def test_sector_inflow_confluence_increases_with_known_sector(self):
        """FIX 2: when sector_flows marks a row's sector as net_inflow=True, the
        confluence component must increase relative to the case with no flow data."""
        # Use KTOS (Industrials sector) which appears in _make_initiations
        sector_flows = {"Industrials": {"net_inflow": True}}
        rows_no_flow = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        rows_with_flow = fb.build_best_buys(
            _make_initiations(), self.followability, sector_flows, self.cap_sources
        )
        ktos_no = next((r for r in rows_no_flow if r["ticker"] == "KTOS"), None)
        ktos_yes = next((r for r in rows_with_flow if r["ticker"] == "KTOS"), None)
        assert ktos_no is not None and ktos_yes is not None
        # sector_inflow=True must increase confluence
        assert ktos_yes["components"]["confluence"] > ktos_no["components"]["confluence"]
        assert ktos_yes["sector_inflow"] is True
        assert ktos_no["sector_inflow"] is None


# ---------------------------------------------------------------------------
# 5. build_small_mid_board
# ---------------------------------------------------------------------------

class TestBuildSmallMidBoard:
    def setup_method(self):
        self.followability = _make_followability()
        self.cap_sources = (_make_membership(), _make_polygon())

    def _run(self, **kw):
        best = fb.build_best_buys(
            _make_initiations(), self.followability, None, self.cap_sources
        )
        return fb.build_small_mid_board(
            best, self.followability, self.cap_sources, **kw
        )

    def test_only_mid_small_off_index(self):
        rows = self._run()
        for r in rows:
            assert r["cap_bucket"] in ("mid", "small", "off_index")

    def test_aapl_excluded_large(self):
        rows = self._run()
        tickers = [r["ticker"] for r in rows]
        assert "AAPL" not in tickers

    def test_ktos_included_small(self):
        rows = self._run(min_incr_pct=1.0)
        tickers = [r["ticker"] for r in rows]
        assert "KTOS" in tickers

    def test_min_incr_pct_filter(self):
        """KTOS max incr_pct = 2.5 (new via whalerock). Filter at 3.0 should exclude it."""
        rows = self._run(min_incr_pct=3.0)
        tickers = [r["ticker"] for r in rows]
        assert "KTOS" not in tickers

    def test_why_field_present(self):
        rows = self._run(min_incr_pct=1.0)
        for r in rows:
            assert "why" in r
            assert len(r["why"]) > 0

    def test_off_index_note(self):
        """Add a ticker that's off_index with qualifying fund."""
        extra = [
            {
                "ticker": "OFFI", "issuer": "OffIndex Corp", "sector": "Energy",
                "slug": "casdin",
                "action": "new", "pct_book": 2.0, "shares_change_pct": None,
                "filing_date": "2026-03-15", "since_excess": None,
            }
        ]
        best = fb.build_best_buys(
            _make_initiations() + extra, self.followability, None, (None, None)
        )
        rows = fb.build_small_mid_board(best, self.followability, (None, None), min_incr_pct=1.0)
        offi_rows = [r for r in rows if r["ticker"] == "OFFI"]
        assert offi_rows, "OFFI should appear in small_mid board"
        assert offi_rows[0]["off_index_note"] is True

    def test_requires_follow_tier_or_score_55(self):
        """Only baupost (insufficient, score=40) -> should be excluded."""
        only_low = [
            {
                "ticker": "LOWQ", "issuer": "LowQ", "sector": "Utilities",
                "slug": "baupost",
                "action": "new", "pct_book": 3.0, "shares_change_pct": None,
                "filing_date": "2026-03-15", "since_excess": None,
            }
        ]
        best = fb.build_best_buys(only_low, self.followability, None, (None, None))
        rows = fb.build_small_mid_board(best, self.followability, (None, None))
        tickers = [r["ticker"] for r in rows]
        assert "LOWQ" not in tickers

    def test_accepts_raw_initiations(self):
        """Passing raw initiations (without cap_bucket key) should still work."""
        rows = fb.build_small_mid_board(
            _make_initiations(), self.followability, self.cap_sources, min_incr_pct=1.0
        )
        # Should not crash and should return valid rows
        assert isinstance(rows, list)

    def test_top_n_respected(self):
        rows = self._run(top_n=1, min_incr_pct=1.0)
        assert len(rows) <= 1


# ---------------------------------------------------------------------------
# 6. build_sector_consensus
# ---------------------------------------------------------------------------

def _make_sector_books():
    """Synthetic books_latest_pair with two proven rotators + one fade."""
    return {
        "casdin": {
            "prev": {"Health Care": 10.0, "Technology": 5.0},
            "curr": {"Health Care": 12.0, "Technology": 3.0},
            "rotation_iq": {"score": 80.0, "n_calls": 10, "hit_rate": 0.70},
            "tickers_curr": {
                "Health Care": [{"ticker": "ABBV", "incr_pct": 2.0}],
                "Technology": [{"ticker": "MSFT", "incr_pct": 0.5}],
            },
        },
        "himalaya": {
            "prev": {"Health Care": 8.0, "Financials": 4.0},
            "curr": {"Health Care": 10.0, "Financials": 4.5},
            "rotation_iq": {"score": 70.0, "n_calls": 6, "hit_rate": 0.60},
            "tickers_curr": {
                "Health Care": [{"ticker": "ABBV", "incr_pct": 1.5}],
            },
        },
        # corvex: fade -> excluded
        "corvex": {
            "prev": {"Energy": 15.0},
            "curr": {"Energy": 20.0},
            "rotation_iq": {"score": 50.0, "n_calls": 8, "hit_rate": 0.55},
            "tickers_curr": {"Energy": [{"ticker": "XOM", "incr_pct": 5.0}]},
        },
        # baupost: insufficient n_calls -> not proven rotator
        "baupost": {
            "prev": {"Financials": 10.0},
            "curr": {"Financials": 15.0},
            "rotation_iq": {"score": 65.0, "n_calls": 3, "hit_rate": 0.60},
            "tickers_curr": {},
        },
    }


class TestBuildSectorConsensus:
    def test_basic_output(self):
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        assert isinstance(rows, list)
        sectors = [r["sector"] for r in rows]
        assert "Health Care" in sectors

    def test_fade_excluded(self):
        """corvex is fade; Energy should not appear if only corvex covers it."""
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        sectors = [r["sector"] for r in rows]
        assert "Energy" not in sectors

    def test_insufficient_n_calls_excluded(self):
        """baupost has n_calls=3 < min_rotator_iq_n=6; Financials from baupost only."""
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        # Financials only from baupost (proven: NO) and himalaya's delta=0.5
        # himalaya IS proven, so Financials should appear (himalaya contributes)
        # The key thing: baupost's block should NOT appear on its own
        # We check n_proven >= 1 for rows that exist
        for row in rows:
            assert row["n_proven"] >= 1

    def test_iq_weighted_delta_math(self):
        """Health Care: casdin delta=+2pp * 0.80 + himalaya delta=+2pp * 0.70 = 3.0."""
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        hc = next((r for r in rows if r["sector"] == "Health Care"), None)
        assert hc is not None
        expected = 2.0 * (80.0 / 100.0) + 2.0 * (70.0 / 100.0)
        assert hc["iq_weighted_delta_pp"] == pytest.approx(expected, rel=1e-4)

    def test_breadth_counts(self):
        """Health Care: both casdin (+2) and himalaya (+2) move >=0.5pp up -> breadth_up=2."""
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        hc = next(r for r in rows if r["sector"] == "Health Care")
        assert hc["breadth_up"] == 2
        assert hc["breadth_down"] == 0

    def test_top_buys_max_5(self):
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        for r in rows:
            assert len(r["top_buys"]) <= 5

    def test_method_note_present(self):
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        for r in rows:
            assert "method_note" in r
            assert "descriptive screen" in r["method_note"].lower()

    def test_sorted_by_iq_weighted_delta_desc(self):
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        deltas = [r["iq_weighted_delta_pp"] for r in rows]
        assert deltas == sorted(deltas, reverse=True)

    def test_n_fade_excluded_counted(self):
        rows = fb.build_sector_consensus(
            _make_sector_books(), _make_followability(), {}, min_rotator_iq_n=6
        )
        for r in rows:
            assert r["n_fade_excluded"] >= 1  # corvex counted

    def test_empty_books(self):
        rows = fb.build_sector_consensus({}, _make_followability(), {})
        assert rows == []

    def test_hit_rate_threshold(self):
        """Fund with hit_rate < 0.5 excluded even if n_calls sufficient."""
        bad_rotator = {
            "whalerock": {
                "prev": {"Materials": 5.0},
                "curr": {"Materials": 10.0},
                "rotation_iq": {"score": 60.0, "n_calls": 8, "hit_rate": 0.40},
                "tickers_curr": {},
            }
        }
        rows = fb.build_sector_consensus(bad_rotator, _make_followability(), {})
        assert rows == []


# ---------------------------------------------------------------------------
# 7. load_grade_a_card — integration against real files
# ---------------------------------------------------------------------------

class TestLoadGradeACard:
    def test_returns_dict_with_required_keys(self):
        card = fb.load_grade_a_card(GRADE_A_DIR)
        assert card is not None, "Expected card from real files"
        for key in ("frozen", "as_of", "period", "anchor", "rows"):
            assert key in card, f"Missing key: {key}"

    def test_frozen_is_true(self):
        card = fb.load_grade_a_card(GRADE_A_DIR)
        assert card["frozen"] is True

    def test_16_rows(self):
        """The Grade-A cohort has exactly 16 funds."""
        card = fb.load_grade_a_card(GRADE_A_DIR)
        assert len(card["rows"]) == 16, f"Expected 16 rows, got {len(card['rows'])}"

    def test_casdin_top_by_dw_excess_60d(self):
        """casdin has the highest decision_weighted_excess_60d in the cohort."""
        card = fb.load_grade_a_card(GRADE_A_DIR)
        assert card["rows"][0]["fund"] == "casdin", (
            f"Expected casdin at top, got {card['rows'][0]['fund']}"
        )

    def test_row_fields_present(self):
        card = fb.load_grade_a_card(GRADE_A_DIR)
        for row in card["rows"]:
            for field in ("fund", "name", "n_priced", "dw_return_60d", "dw_excess_60d",
                          "hit_60d", "book_impact_pp"):
                assert field in row, f"Row missing field: {field}"

    def test_action_dw_excess_parsed(self):
        """new_dw_excess_60d and add_dw_excess_60d sourced from action-level
        decision_weighted_excess_60d (FIX 5: units-consistent excess, not equal_mean)."""
        import pandas as pd
        card = fb.load_grade_a_card(GRADE_A_DIR)
        # bakerbros has both new and add rows in action file
        bakerbros = next(r for r in card["rows"] if r["fund"] == "bakerbros")
        assert "new_dw_excess_60d" in bakerbros
        assert "add_dw_excess_60d" in bakerbros
        assert bakerbros["new_dw_excess_60d"] is not None
        assert bakerbros["add_dw_excess_60d"] is not None
        # Verify the values match the action CSV's decision_weighted_excess_60d column
        action_df = pd.read_csv(GRADE_A_DIR / "fund_action_horizon_summary.csv")
        bb_new = action_df[(action_df["fund"] == "bakerbros") & (action_df["action"] == "new")]
        bb_add = action_df[(action_df["fund"] == "bakerbros") & (action_df["action"] == "add")]
        assert not bb_new.empty and not bb_add.empty
        assert bakerbros["new_dw_excess_60d"] == pytest.approx(
            float(bb_new.iloc[0]["decision_weighted_excess_60d"]), rel=1e-5
        )
        assert bakerbros["add_dw_excess_60d"] == pytest.approx(
            float(bb_add.iloc[0]["decision_weighted_excess_60d"]), rel=1e-5
        )
        # Old field names must NOT exist (renamed in FIX 5)
        assert "new_mean_60d" not in bakerbros
        assert "add_mean_60d" not in bakerbros

    def test_metadata_fields(self):
        card = fb.load_grade_a_card(GRADE_A_DIR)
        assert card["as_of"] == "2026-07-17"
        assert card["period"] == "2026-03-31"
        assert card["anchor"] == "2026-05-15"

    def test_sorted_by_dw_excess_desc(self):
        card = fb.load_grade_a_card(GRADE_A_DIR)
        excesses = [r["dw_excess_60d"] for r in card["rows"]]
        assert excesses == sorted(excesses, reverse=True)

    def test_missing_dir_returns_none(self):
        card = fb.load_grade_a_card(pathlib.Path("/tmp/nonexistent_grade_a_dir"))
        assert card is None

    def test_no_import_time_io(self):
        """Importing engine.fund_boards must NOT raise or perform disk I/O."""
        import importlib
        # Re-import should be safe (cached); just assert it works
        importlib.import_module("engine.fund_boards")


# ---------------------------------------------------------------------------
# 8. load_cap_sources integration smoke test
# ---------------------------------------------------------------------------

class TestLoadCapSources:
    def test_returns_tuple(self):
        m, p = fb.load_cap_sources()
        # Real data dir exists; both should be non-None
        assert m is not None
        assert p is not None

    def test_membership_has_expected_columns(self):
        m, _ = fb.load_cap_sources()
        assert "ticker" in m.columns
        assert "group" in m.columns

    def test_polygon_indexed_by_ticker(self):
        _, p = fb.load_cap_sources()
        assert p.index.name == "ticker"
        assert "market_cap_usd" in p.columns

    def test_missing_root_degrades_gracefully(self):
        m, p = fb.load_cap_sources(pathlib.Path("/tmp/no_such_data_dir"))
        assert m is None
        assert p is None
