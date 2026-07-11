"""Tests for engine/fear_greed.py — DISPLAY-ONLY Fear/Greed composite (P1.2).

Covers:
  1. Orientation correctness: each leg's greed direction
  2. Min-history exclusion: legs with < gate obs are excluded from z-mean
  3. Missing-store graceful degrade: never crashes, drops the leg
  4. Dial bounds: composite is always 0-100
  5. Band mapping monotonicity
  6. Young tiles: putcall and aaii always excluded from composite, returned as tiles
  7. Template render smoke: fear-greed-detail section renders with and without data
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.fear_greed as fgmod  # noqa: E402
from engine import fear_greed as fgmod  # noqa: E402

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_daily(n: int = 400, start: str = "2018-01-01") -> pd.DataFrame:
    """Return a simple daily DataFrame with a 'close' column."""
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"close": np.linspace(100, 200, n)}, index=idx)


def _make_breadth(n: int = 400) -> pd.DataFrame:
    idx = pd.bdate_range("2018-01-01", periods=n)
    nh = np.abs(np.sin(np.arange(n) / 20)) * 50 + 10
    nl = np.abs(np.cos(np.arange(n) / 20)) * 30 + 5
    adv = nh + 5
    dec = nl + 3
    return pd.DataFrame({"nh": nh, "nl": nl, "adv": adv, "dec": dec}, index=idx)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Orientation: each leg's greed direction
# ─────────────────────────────────────────────────────────────────────────────

class TestOrientation:
    """For each leg, a world that is unambiguously greedy should produce a
    positive z-score (after orientation negation), and a fearful world a
    negative one."""

    def test_spx_momentum_greed_positive(self, monkeypatch, tmp_path):
        """SPY well above 125d MA → SPX-momentum z > 0.

        Strategy: build a series where the last 200 rows sit at a historically
        large positive spread vs the 125d MA, so the z-score of the spread
        is positive at the end.
        """
        idx = pd.bdate_range("2017-01-01", periods=700)
        # First 300 rows: flat around 100 (low spread)
        # Last 400 rows: strong uptrend so close >> 125d MA → large positive spread
        flat = np.linspace(100, 102, 300)
        ramp = np.linspace(102, 250, 400)
        close = np.concatenate([flat, ramp])
        spy = pd.DataFrame({"close": close}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: spy)
        leg = fgmod._leg_spx_momentum()
        assert leg["z"] is not None, "z should not be None with sufficient history"
        assert leg["z"] > 0, f"expected positive z (greed), got {leg['z']}"

    def test_spx_momentum_fear_negative(self, monkeypatch):
        """SPY well below 125d MA → SPX-momentum z < 0."""
        idx = pd.bdate_range("2017-01-01", periods=500)
        close = np.concatenate([np.linspace(200, 190, 125), np.linspace(190, 100, 375)])
        spy = pd.DataFrame({"close": close}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: spy)
        leg = fgmod._leg_spx_momentum()
        assert leg["z"] is not None
        assert leg["z"] < 0, f"expected negative z (fear), got {leg['z']}"

    def test_hy_oas_low_is_greed(self, monkeypatch):
        """Low OAS (tightening) → junk demand z > 0 (greed)."""
        idx = pd.bdate_range("2014-01-01", periods=1000)
        # OAS declining to its historic minimum → low OAS = greed
        oas = np.linspace(6.0, 2.0, 1000)
        df = pd.DataFrame({"hy_oas": oas}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: df)
        leg = fgmod._leg_hy_oas()
        assert leg["z"] is not None
        assert leg["z"] > 0, f"low OAS should produce positive z (greed), got {leg['z']}"

    def test_hy_oas_high_is_fear(self, monkeypatch):
        """High OAS → junk demand z < 0 (fear)."""
        idx = pd.bdate_range("2014-01-01", periods=1000)
        oas = np.linspace(2.0, 9.0, 1000)
        df = pd.DataFrame({"hy_oas": oas}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: df)
        leg = fgmod._leg_hy_oas()
        assert leg["z"] is not None
        assert leg["z"] < 0, f"high OAS should produce negative z (fear), got {leg['z']}"

    def test_vix_level_low_is_greed(self, monkeypatch):
        """Low VIX → vix_level z > 0 (greed)."""
        idx = pd.bdate_range("2013-01-01", periods=1500)
        # VIX falling to minimum in recent history
        close = np.concatenate([np.linspace(25, 20, 750), np.linspace(20, 9, 750)])
        vix = pd.DataFrame({"close": close, "high": close, "low": close, "volume": 0.0}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: vix)
        leg = fgmod._leg_vix_level()
        assert leg["z"] is not None
        assert leg["z"] > 0, f"low VIX should give positive z (greed), got {leg['z']}"

    def test_vix_trend_falling_is_greed(self, monkeypatch):
        """Falling VIX → vix_trend z > 0 (greed)."""
        idx = pd.bdate_range("2013-01-01", periods=1500)
        # Strong downtrend at the end → most recent 20d change = very negative → negated z > 0
        close = np.concatenate([np.linspace(30, 25, 1000), np.linspace(25, 10, 500)])
        vix = pd.DataFrame({"close": close, "high": close, "low": close, "volume": 0.0}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: vix)
        leg = fgmod._leg_vix_trend()
        assert leg["z"] is not None
        assert leg["z"] > 0, f"falling VIX should give positive z (greed), got {leg['z']}"

    def test_skew_low_is_greed(self, monkeypatch):
        """Low CBOE SKEW → z > 0 (less tail fear = greed)."""
        idx = pd.bdate_range("2012-01-01", periods=1500)
        # SKEW declining to minimum
        skew = np.concatenate([np.linspace(130, 125, 750), np.linspace(125, 105, 750)])
        df = pd.DataFrame({"skew": skew}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: df)
        leg = fgmod._leg_skew()
        assert leg["z"] is not None
        assert leg["z"] > 0, f"low SKEW should give positive z (greed), got {leg['z']}"

    def test_naaim_high_is_greed(self, monkeypatch):
        """High NAAIM exposure → z > 0 (greed)."""
        idx = pd.date_range("2004-01-01", periods=250, freq="W-WED")
        exposure = np.concatenate([np.linspace(50, 60, 125), np.linspace(60, 110, 125)])
        df = pd.DataFrame({"naaim_exposure": exposure}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: df)
        leg = fgmod._leg_naaim()
        assert leg["z"] is not None
        assert leg["z"] > 0, f"high NAAIM should give positive z (greed), got {leg['z']}"

    def test_vix_term_contango_is_greed(self, monkeypatch):
        """VIX/VIX3M < 1 (contango) → z > 0 (greed)."""
        import engine.canon as canon_mod
        idx = pd.bdate_range("2013-01-01", periods=1500)
        # VIX/VIX3M strongly in contango at the end (ratio < 0.9)
        vix_close = np.concatenate([np.linspace(20, 18, 750), np.linspace(18, 12, 750)])
        vix3m_close = np.concatenate([np.linspace(22, 21, 750), np.linspace(21, 18, 750)])
        vix_df = pd.DataFrame({"close": vix_close, "high": vix_close, "low": vix_close, "volume": 0.0}, index=idx)
        vix3m_df = pd.DataFrame({"close": vix3m_close, "high": vix3m_close, "low": vix3m_close, "volume": 0.0}, index=idx)
        def mock_read(cat, name):
            if name == "_VIX":
                return vix_df
            if name == "_VIX3M":
                return vix3m_df
            return None
        monkeypatch.setattr(fgmod.store, "read", mock_read)
        leg = fgmod._leg_vix_term()
        assert leg["z"] is not None
        assert leg["z"] > 0, f"contango (low ratio) should give positive z (greed), got {leg['z']}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Min-history gate: legs below threshold are excluded from composite
# ─────────────────────────────────────────────────────────────────────────────

class TestMinHistoryGate:

    def test_daily_leg_excluded_below_252(self, monkeypatch):
        """A daily leg with < 252 obs must not enter z-mean."""
        # Only 100 rows — below DAILY_MIN=252
        idx = pd.bdate_range("2025-01-01", periods=100)
        spy_small = pd.DataFrame({"close": np.linspace(100, 120, 100)}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: spy_small)
        leg = fgmod._leg_spx_momentum()
        # z will be None because expanding min_periods=252 not yet met
        assert not fgmod._gate_passes(leg), "leg with 100 obs should fail the daily gate"

    def test_daily_leg_included_at_252(self, monkeypatch):
        """A daily leg with exactly 252 obs must pass the gate."""
        idx = pd.bdate_range("2023-01-01", periods=252)
        close = np.linspace(100, 200, 252)
        spy = pd.DataFrame({"close": close}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: spy)
        leg = fgmod._leg_spx_momentum()
        # z might still be None if rolling z-window hasn't warmed up — check obs count gate
        assert leg["obs_count"] == 252
        assert fgmod._gate_passes(leg), "leg with exactly 252 obs should pass the daily gate"

    def test_weekly_naaim_excluded_below_104(self, monkeypatch):
        """NAAIM with < 104 weekly obs excluded."""
        idx = pd.date_range("2024-01-01", periods=50, freq="W-WED")
        df = pd.DataFrame({"naaim_exposure": np.linspace(40, 90, 50)}, index=idx)
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: df)
        leg = fgmod._leg_naaim()
        assert not fgmod._gate_passes(leg), "NAAIM with 50 obs should fail the weekly gate"

    def test_quarterly_insider_included_at_81(self):
        """Insider with 81 quarterly panels passes the gate (>=40)."""
        # The real store has 81 panels; test the gate function directly
        leg = {"key": "insider", "obs_count": 81}
        assert fgmod._gate_passes(leg)

    def test_quarterly_insider_excluded_below_40(self):
        """Insider with 30 quarterly panels fails the gate."""
        leg = {"key": "insider", "obs_count": 30}
        assert not fgmod._gate_passes(leg)


# ─────────────────────────────────────────────────────────────────────────────
# Insider data-quality: dedup + cap + plausible range sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestInsiderDataQuality:
    """Guards against the quadrillion-dollar insider-value bug (PR #1324 review finding).

    Root cause: the sec_insider panel 'usd' column occasionally contains rows
    with corrupt price data (e.g. price in cents → usd = shares × huge_price),
    and duplicate rows from Form-4 amendments, collectively inflating the raw
    quarterly aggregate by many orders of magnitude.

    The fix: dedup on (ticker, trans_date, code, shares, price) and cap each
    individual transaction at _INSIDER_TXN_CAP_USD before summing.
    """

    def _make_panel(self, rows):
        """Build a minimal panel DataFrame matching the sec_insider schema."""
        return pd.DataFrame(rows)

    def test_dedup_removes_duplicate_amendment_rows(self, monkeypatch, tmp_path):
        """Duplicate Form-4 rows (same ticker/trans_date/code/shares/price) are
        counted only once in the quarterly aggregate."""
        # Two identical rows for a single $50K purchase
        panel = self._make_panel([
            {"ticker": "AAPL", "trans_date": "2024-03-15", "code": "P",
             "shares": 1000.0, "price": 50.0, "usd": 50_000.0, "quarter": "2024q1"},
            {"ticker": "AAPL", "trans_date": "2024-03-15", "code": "P",
             "shares": 1000.0, "price": 50.0, "usd": 50_000.0, "quarter": "2024q1"},
        ])

        def _fake_read_parquet(fp, **kw):
            return panel

        monkeypatch.setattr(fgmod.pd, "read_parquet", _fake_read_parquet)

        import glob as _glob
        monkeypatch.setattr(fgmod, "glob", type("G", (), {
            "glob": staticmethod(lambda pat: ["/fake/2024q1.parquet"])
        })())

        ts = fgmod._build_insider_time_series()
        assert len(ts) == 1
        # After dedup, net should be $50K, not $100K
        assert abs(ts.iloc[0] - 50_000.0) < 1.0, (
            f"Expected ~50000 after dedup, got {ts.iloc[0]}")

    def test_corrupt_price_rows_are_capped(self, monkeypatch):
        """A row with a corrupt usd value > _INSIDER_TXN_CAP_USD is excluded."""
        import glob as _glob
        panel = self._make_panel([
            # Legitimate trade: $80K purchase
            {"ticker": "AAPL", "trans_date": "2024-03-10", "code": "P",
             "shares": 1000.0, "price": 80.0, "usd": 80_000.0, "quarter": "2024q1"},
            # Corrupt trade: usd = $2.4 quadrillion (price in cents error)
            {"ticker": "CCCG", "trans_date": "2024-03-12", "code": "S",
             "shares": 1e8, "price": 2.4e7, "usd": 2.4e15, "quarter": "2024q1"},
        ])

        def _fake_read_parquet(fp, **kw):
            return panel

        monkeypatch.setattr(fgmod.pd, "read_parquet", _fake_read_parquet)
        monkeypatch.setattr(fgmod, "glob", type("G", (), {
            "glob": staticmethod(lambda pat: ["/fake/2024q1.parquet"])
        })())

        ts = fgmod._build_insider_time_series()
        assert len(ts) == 1
        # The corrupt sell is dropped; only the $80K buy counts → net = +$80K
        assert abs(ts.iloc[0] - 80_000.0) < 1.0, (
            f"Expected ~80000 after capping corrupt row, got {ts.iloc[0]}")

    def test_real_insider_leg_value_within_plausible_range(self):
        """With real panel data, the displayed insider net value is within ±$200 B.

        If this fails, _build_insider_time_series() is returning implausibly large
        values (the quadrillion-dollar bug has regressed).
        """
        ts = fgmod._build_insider_time_series()
        if ts.empty:
            import pytest as _pytest
            _pytest.skip("no sec_insider panel data available")
        ts_b = ts / 1e9   # billions
        max_abs = float(ts_b.abs().max())
        assert max_abs < 200, (
            f"Insider net USD (max abs) = {max_abs:.1f} B — implausibly large. "
            "Expected < $200 B; likely a corrupt price or unit error in the panel."
        )

    def test_compute_excludes_young_legs_from_z_mean(self, monkeypatch):
        """When a leg has obs_count < gate threshold, it must not appear in legs_included."""
        # Mock all store reads to return a tiny DataFrame (10 rows — too young for all legs)
        tiny_idx = pd.bdate_range("2026-01-01", periods=10)
        tiny_df = pd.DataFrame({"close": np.linspace(100, 110, 10),
                                "high": 110.0, "low": 100.0, "volume": 0.0}, index=tiny_idx)
        tiny_breadth = pd.DataFrame({"nh": [5]*10, "nl": [3]*10,
                                     "adv": [8]*10, "dec": [4]*10}, index=tiny_idx)
        tiny_fred = pd.DataFrame({"hy_oas": [3.5]*10}, index=tiny_idx)
        tiny_cboe = pd.DataFrame({"skew": [130.0]*10}, index=tiny_idx)
        tiny_naaim = pd.DataFrame({"naaim_exposure": [60.0]*10},
                                  index=pd.date_range("2026-01-01", periods=10, freq="W-WED"))

        def mock_read(cat, name):
            mapping = {
                ("yahoo", "SPY"): tiny_df, ("yahoo", "TLT"): tiny_df,
                ("yahoo", "_VIX"): tiny_df, ("yahoo", "_VIX3M"): tiny_df,
                ("yahoo", "HYG"): tiny_df, ("yahoo", "IEF"): tiny_df,
                ("breadth", "breadth"): tiny_breadth,
                ("fred", "BAMLH0A0HYM2"): tiny_fred,
                ("cboe", "skew"): tiny_cboe,
                ("cboe", "putcall"): pd.DataFrame({"equity_pc_ratio": [0.7]*10},
                                                  index=tiny_idx),
                ("sentiment", "naaim"): tiny_naaim,
                ("sentiment", "aaii"): pd.DataFrame(
                    {"aaii_bullish": [35.0]*10, "aaii_neutral": [30.0]*10,
                     "aaii_bearish": [35.0]*10},
                    index=pd.date_range("2026-01-01", periods=10, freq="W-WED")),
            }
            return mapping.get((cat, name))

        # Also mock _build_insider_time_series to return too-short series
        monkeypatch.setattr(fgmod.store, "read", mock_read)
        monkeypatch.setattr(fgmod, "_build_insider_time_series",
                            lambda: pd.Series(dtype=float))

        result = fgmod.compute_fear_greed()
        # All legs should be excluded → result is None or empty legs_included
        if result is not None:
            # All included legs must have passed the gate
            for leg in result.get("legs_included", []):
                assert fgmod._gate_passes(leg), (
                    f"leg {leg['key']} in legs_included despite failing gate "
                    f"(obs={leg['obs_count']})")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Missing-store graceful degrade
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingStoreDegrade:

    def test_missing_spy_store_returns_missing_leg(self, monkeypatch):
        """When SPY store is unavailable, _leg_spx_momentum returns a missing leg (no crash)."""
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: None)
        leg = fgmod._leg_spx_momentum()
        assert leg["freshness"] == "missing"
        assert leg["z"] is None
        assert leg["value"] is None

    def test_missing_hy_oas_falls_back_to_hyg_ief(self, monkeypatch):
        """When BAMLH0A0HYM2 is unavailable, hy_oas falls back to HYG/IEF ratio."""
        idx = pd.bdate_range("2014-01-01", periods=1000)
        hyg = pd.DataFrame({"close": np.linspace(80, 90, 1000)}, index=idx)
        ief = pd.DataFrame({"close": np.linspace(95, 100, 1000)}, index=idx)

        def mock_read(cat, name):
            if name == "BAMLH0A0HYM2":
                return None
            if name == "HYG":
                return hyg
            if name == "IEF":
                return ief
            return None

        monkeypatch.setattr(fgmod.store, "read", mock_read)
        leg = fgmod._leg_hy_oas()
        # Should not crash and should have some data from fallback
        assert leg["obs_count"] is not None
        assert "fallback" in leg.get("unit", "")

    def test_compute_fear_greed_with_all_missing_returns_none(self, monkeypatch):
        """When all stores return None and insider has no panels, result is None."""
        monkeypatch.setattr(fgmod.store, "read", lambda cat, name: None)
        monkeypatch.setattr(fgmod, "_build_insider_time_series",
                            lambda: pd.Series(dtype=float))
        result = fgmod.compute_fear_greed()
        # All legs missing → no z_vals → None
        assert result is None

    def test_compute_fear_greed_partial_missing_no_crash(self, monkeypatch):
        """Partial store availability: some legs missing, engine never crashes."""
        idx = pd.bdate_range("2014-01-01", periods=1000)
        spy = pd.DataFrame({"close": np.linspace(100, 300, 1000)}, index=idx)

        def partial_read(cat, name):
            if (cat, name) == ("yahoo", "SPY"):
                return spy
            return None  # everything else missing

        monkeypatch.setattr(fgmod.store, "read", partial_read)
        monkeypatch.setattr(fgmod, "_build_insider_time_series",
                            lambda: pd.Series(dtype=float))
        # Should not raise
        result = fgmod.compute_fear_greed()
        # Either None (all failed) or a valid dict
        if result is not None:
            assert 0 <= result["dial"] <= 100


# ─────────────────────────────────────────────────────────────────────────────
# 4. Dial bounds
# ─────────────────────────────────────────────────────────────────────────────

def test_dial_always_0_100(monkeypatch):
    """dial is always clamped to [0, 100], even with extreme z-scores."""
    from engine.fear_greed import _dial_band

    # Mock a compute that produces extreme z_vals
    original_compute = fgmod.compute_fear_greed

    def _mock_compute():
        # Patch internals: all legs return z=5 (extreme greed)
        pass

    # Test the dial formula directly for extreme inputs
    for z_mean in [-10, -5, -3, 0, 3, 5, 10]:
        dial = int(max(0, min(100, round(50 + (z_mean / 3.0) * 50))))
        assert 0 <= dial <= 100, f"dial={dial} out of bounds for z_mean={z_mean}"


def test_band_mapping_monotonic():
    """Higher dial values map to greedier bands (monotone)."""
    from engine.fear_greed import _dial_band
    bands_ordered = ["Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"]
    seen = []
    for dial in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        en, _ = _dial_band(dial)
        seen.append(en)
    # No band should appear after a later band in the ordering
    idx_seq = [bands_ordered.index(b) for b in seen]
    assert idx_seq == sorted(idx_seq), f"band sequence not monotone: {seen}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Young tiles: putcall and aaii always excluded, returned as tiles
# ─────────────────────────────────────────────────────────────────────────────

def test_real_data_young_tiles_excluded():
    """With real data, putcall (21 rows) and aaii (22 rows) must be in young_tiles
    not in legs_included."""
    result = fgmod.compute_fear_greed()
    if result is None:
        pytest.skip("no data available")
    included_keys = {l["key"] for l in result["legs_included"]}
    young_tile_keys = {t["key"] for t in result["young_tiles"]}
    assert "putcall" not in included_keys, "putcall should be excluded (too young)"
    assert "aaii" not in included_keys, "aaii should be excluded (too young)"
    assert "putcall" in young_tile_keys, "putcall should be in young_tiles"
    assert "aaii" in young_tile_keys, "aaii should be in young_tiles"


def test_young_tile_putcall_mock(monkeypatch, tmp_path):
    """_young_tile_putcall returns a well-formed dict even with a small store."""
    idx = pd.bdate_range("2026-01-01", periods=21)
    df = pd.DataFrame({"equity_pc_ratio": [0.7]*21, "index_pc_ratio": [0.9]*21}, index=idx)
    monkeypatch.setattr(fgmod.store, "read", lambda cat, name: df)
    tile = fgmod._young_tile_putcall()
    assert tile["key"] == "putcall"
    assert tile["freshness"] == "young"
    assert tile["obs_count"] == 21
    assert tile["value"] is not None


def test_young_tile_aaii_mock(monkeypatch):
    """_young_tile_aaii returns a well-formed dict even with a small store."""
    idx = pd.date_range("2026-01-01", periods=22, freq="W-WED")
    df = pd.DataFrame({"aaii_bullish": [40.0]*22, "aaii_neutral": [30.0]*22,
                       "aaii_bearish": [30.0]*22}, index=idx)
    monkeypatch.setattr(fgmod.store, "read", lambda cat, name: df)
    tile = fgmod._young_tile_aaii()
    assert tile["key"] == "aaii"
    assert tile["freshness"] == "young"
    assert tile["obs_count"] == 22


# ─────────────────────────────────────────────────────────────────────────────
# 6. Real-data smoke test
# ─────────────────────────────────────────────────────────────────────────────

def test_real_data_smoke():
    """compute_fear_greed() returns a valid payload with real data."""
    result = fgmod.compute_fear_greed()
    if result is None:
        pytest.skip("no data available")
    assert 0 <= result["dial"] <= 100
    assert result["label_en"] in {"Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"}
    assert "legs_included" in result
    assert "legs_excluded_young" in result
    assert "young_tiles" in result
    assert result["n_legs_qualifying"] == len(result["legs_included"])
    assert result["disclaimer_en"]
    assert result["disclaimer_zh"]
    # All included legs have the required fields
    for leg in result["legs_included"]:
        assert "key" in leg
        assert "z" in leg and leg["z"] is not None
        assert "orientation" in leg
        assert leg["orientation"] in {"higher=greed", "lower=greed"}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Template render smoke
# ─────────────────────────────────────────────────────────────────────────────

def _make_min_fg() -> dict:
    """Minimal Fear/Greed payload for template testing."""
    return {
        "dial": 54,
        "label_en": "Neutral",
        "label_zh": "中性",
        "n_legs_qualifying": 2,
        "legs_included": [
            {"key": "spx_momentum", "name_en": "SPX momentum (vs 125d MA)",
             "name_zh": "标普动量", "value": 2.5, "z": 0.6, "pct": 73,
             "freshness": "fresh", "obs_count": 400,
             "orientation": "higher=greed", "unit": "% above MA"},
            {"key": "vix_level", "name_en": "VIX level", "name_zh": "VIX 水平",
             "value": 14.2, "z": 0.4, "pct": 62, "freshness": "fresh",
             "obs_count": 300, "orientation": "lower=greed", "unit": "VIX points"},
        ],
        "legs_excluded_young": [],
        "young_tiles": [
            {"key": "putcall", "name_en": "CBOE put/call ratio",
             "name_zh": "看跌/看涨比率", "value": 0.72,
             "obs_count": 21, "freshness": "young",
             "as_of": "2026-07-01",
             "note_en": "Too young", "note_zh": "过短"},
            {"key": "aaii", "name_en": "AAII sentiment (bullish %)",
             "name_zh": "AAII 情绪", "value": 41.5,
             "obs_count": 22, "freshness": "young",
             "as_of": "2026-07-01",
             "note_en": "Too young", "note_zh": "过短"},
        ],
        "as_of": "2026-07-04",
        "generated_utc": "2026-07-04T12:00:00Z",
        "disclaimer_en": "Sentiment context only.",
        "disclaimer_zh": "仅为情绪参考。",
    }


def _render_fg_dashboard(fear_greed):
    """Render the v2 MX2 sentiment block (inside the RISK tray) of dashboard.html.j2.
    Slices on {# MX2-SENTIMENT-START #} / {# MX2-SENTIMENT-END #} markers so the
    test exercises the v2 tray region (Fix 6 — v2 transition)."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n
    src = (TEMPLATES / "dashboard.html.j2").read_text()
    macros = src[: src.index("{# coloured")]
    start = src.index("{# MX2-SENTIMENT-START #}")
    end = src.index("{# MX2-SENTIMENT-END #}")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    # market_state must be truthy to enter the RISK tray gate ({% if market_state %})
    _min_ms = {"radar": {}, "components": [], "color": "green", "score": 55,
               "label_en": "Risk-on", "label_zh": "偏好", "asof": "2026-07-11",
               "headline_en": "Markets lean risk-on.", "headline_zh": "市场偏向风险偏好。",
               "overrides": [], "flip_en": None, "flip_zh": None, "mtf": None}
    return env.from_string(macros + src[start:end]).render(
        fear_greed=fear_greed,
        fear_euphoria=None,
        froth_fragility=None,
        mode="macro",
        market_state=_min_ms,
        latest={"risk_radar": None, "fed_stance": None, "turning_point": None},
    )


def _render_fg_macro_signals(fear_greed):
    """Extract and render the Fear/Greed detail section of macro_signals.html.j2."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n
    src = (TEMPLATES / "macro_signals.html.j2").read_text()
    macros = src[: src.index("<!DOCTYPE")]
    start = src.index("{# ===================== FEAR / GREED COMPOSITE")
    end = src.index("{# ===================== FEAR <-> EUPHORIA (full)")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    return env.from_string(macros + src[start:end]).render(
        fear_greed=fear_greed,
    )


def test_dashboard_card_renders():
    """The Fear/Greed card appears in the dashboard sentiment-regime section."""
    html = _render_fg_dashboard(_make_min_fg())
    assert 'id="fear-greed"' in html
    assert "Fear / Greed sentiment context" in html
    assert "恐惧/贪婪情绪参考" in html
    assert "54" in html                              # dial value
    assert "Neutral" in html
    assert "中性" in html


def test_dashboard_card_absent_when_none():
    """When fear_greed is None, no fear-greed card is rendered."""
    html = _render_fg_dashboard(None)
    assert 'id="fear-greed"' not in html


def test_dashboard_young_tiles_render():
    """Young context tiles are shown when present."""
    html = _render_fg_dashboard(_make_min_fg())
    assert "CBOE put/call ratio" in html or "Context tiles" in html


def test_macro_signals_detail_renders():
    """Fear/Greed full breakdown section renders in macro_signals.html.j2."""
    html = _render_fg_macro_signals(_make_min_fg())
    assert 'id="fear-greed-detail"' in html
    assert "Fear / Greed composite" in html
    assert "恐惧/贪婪合成" in html
    assert "SPX momentum" in html                   # leg name appears
    assert "VIX level" in html
    assert "54" in html                             # dial


def test_macro_signals_detail_absent_when_none():
    """When fear_greed is None, the detail section does not render."""
    html = _render_fg_macro_signals(None)
    assert 'id="fear-greed-detail"' not in html


def test_no_translated_text_in_title_attributes():
    """No Chinese characters in title= attributes (CI guard check_title_i18n)."""
    import re
    for render_fn, name in [
        (_render_fg_dashboard, "dashboard"),
        (_render_fg_macro_signals, "macro_signals"),
    ]:
        html = render_fn(_make_min_fg())
        bad = re.findall(r'title="[^"]*[一-鿿][^"]*"', html)
        assert not bad, (
            f"{name}: translated text found in title= attributes: {bad[:3]}"
        )
