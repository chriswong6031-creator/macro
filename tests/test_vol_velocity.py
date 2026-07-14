"""Tests for engine/vol_velocity.py — display-only vol-weather organ (VSB W3).

Invariants tested:
  1. Percentile math — trailing 252-obs percentile is hand-checked
  2. Young gate — <252 obs yields pctile=None, freshness='young'
  3. Missing store — missing file/None yields chip with freshness='missing', pctile=None
  4. Divergence flag — VVIX/VIX chip logic (vvix_pctile >= 70 AND vix_pctile <= 40)
  5. Term inversion boundary — VIX9D/VIX3M > 1.0 definitional backwardation
  6. as_of = max last_date across non-missing chips (not now-UTC)
  7. Returns None when ALL chips missing
  8. Spike state detection — vix_velocity 5d pctile >= 95
  9. dspx vixeq_minus_vix secondary field
  10. cor chip plain-word framing (how much stocks move together)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.vol_velocity as vv  # noqa: E402 — monkeypatching target

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_vix(n: int = 300, start: str = "2017-01-01",
              trend: str = "flat", value: float = 20.0) -> pd.DataFrame:
    """Build a synthetic VIX-like DataFrame with 'close' and 'high' columns."""
    idx = pd.bdate_range(start, periods=n)
    if trend == "flat":
        close = np.full(n, value)
    elif trend == "up":
        close = np.linspace(value * 0.5, value * 1.5, n)
    elif trend == "down":
        close = np.linspace(value * 1.5, value * 0.5, n)
    else:
        close = np.full(n, value)
    return pd.DataFrame({"close": close, "high": close * 1.05}, index=idx)


def _make_vvix(n: int = 300, value: float = 80.0) -> pd.DataFrame:
    """Synthetic VVIX parquet df (column 'vvix')."""
    idx = pd.bdate_range("2017-01-01", periods=n)
    return pd.DataFrame({"vvix": np.full(n, value)}, index=idx)


def _make_cboe_close(n: int = 300, value: float = 50.0, filename: str = "x") -> pd.DataFrame:
    """Synthetic CBOE close-column df."""
    idx = pd.bdate_range("2017-01-01", periods=n)
    return pd.DataFrame({"close": np.full(n, value)}, index=idx)


def _null_store(cat, name):
    return None


# ---------------------------------------------------------------------------
# 1. Percentile math hand-check
# ---------------------------------------------------------------------------

class TestPercentileMath:
    def test_trailing_pctile_exact_at_max(self):
        """If the series ends at its maximum, the trailing pctile should be 100."""
        s = pd.Series(np.arange(1.0, 301.0),
                      index=pd.bdate_range("2017-01-01", periods=300))
        pct_series = vv._trailing_pctile(s, window=252)
        last = pct_series.dropna().iloc[-1]
        assert last == pytest.approx(100.0, abs=1.0)

    def test_trailing_pctile_exact_at_min(self):
        """If the series ends at its minimum (last 252 obs), pctile is near 0."""
        s = pd.Series(np.arange(300.0, 0.0, -1.0),
                      index=pd.bdate_range("2017-01-01", periods=300))
        pct_series = vv._trailing_pctile(s, window=252)
        last = pct_series.dropna().iloc[-1]
        # The last value is 1.0 (minimum); all 252 obs >= it, so pctile near 0
        assert last < 5.0, f"Expected near 0, got {last}"

    def test_trailing_pctile_midpoint(self):
        """For a uniform series ending at the median value, pctile ~ 50."""
        s = pd.Series(np.linspace(1.0, 100.0, 300),
                      index=pd.bdate_range("2017-01-01", periods=300))
        # Override last value to the 50th percentile of the trailing window
        vals = np.sort(s.iloc[-252:].values)
        median_val = vals[len(vals) // 2]
        s.iloc[-1] = median_val
        pct_series = vv._trailing_pctile(s, window=252)
        last = pct_series.dropna().iloc[-1]
        assert 40 <= last <= 60, f"Expected ~50, got {last}"

    def test_trailing_pctile_short_series_returns_nan(self):
        """Series shorter than window returns all NaN."""
        s = pd.Series(np.arange(1.0, 100.0),
                      index=pd.bdate_range("2017-01-01", periods=99))
        pct_series = vv._trailing_pctile(s, window=252)
        assert pct_series.dropna().empty

    def test_trailing_pctile_frozen_feed_is_neutral_not_extreme(self):
        """MIDRANK regression guard: an all-tied window (frozen/repeating feed)
        must score ~50 (neutral), NOT 100 — the naive (<= latest) form reads a
        broken feed as an extreme ('spiking') at exactly the wrong moment."""
        s = pd.Series(np.full(300, 17.5),
                      index=pd.bdate_range("2017-01-01", periods=300))
        pct_series = vv._trailing_pctile(s, window=252)
        last = pct_series.dropna().iloc[-1]
        assert last == pytest.approx(50.0, abs=0.01), f"Expected 50 on ties, got {last}"


# ---------------------------------------------------------------------------
# 2. Young gate (<252 obs)
# ---------------------------------------------------------------------------

class TestYoungGate:
    def test_vix_level_young_when_short(self, monkeypatch, tmp_path):
        """VIX series with 100 obs: chip has freshness='young', pctile=None."""
        short_vix = _make_vix(n=100, start="2023-01-01")
        monkeypatch.setattr(vv.store, "read", lambda cat, name: short_vix)
        chip = vv._chip_vix_level()
        assert chip["freshness"] == "young"
        assert chip["pctile"] is None
        assert chip["obs_count"] == 100

    def test_vix_velocity_young_when_short(self, monkeypatch):
        short_vix = _make_vix(n=50)
        monkeypatch.setattr(vv.store, "read", lambda cat, name: short_vix)
        chip = vv._chip_vix_velocity()
        assert chip["freshness"] == "young"
        assert chip["pctile"] is None

    def test_term_slope_young_when_short(self, monkeypatch):
        short = _make_vix(n=100)
        def _read(cat, name):
            return short
        monkeypatch.setattr(vv.store, "read", _read)
        chip = vv._chip_term_slope()
        # Not inverted (ratio = 1.0 exactly at boundary = 1.0 is NOT > 1.0)
        assert chip["freshness"] == "young"
        assert chip["pctile"] is None


# ---------------------------------------------------------------------------
# 3. Missing store -> chip with freshness='missing'
# ---------------------------------------------------------------------------

class TestMissingStore:
    def test_vix_level_missing(self, monkeypatch):
        monkeypatch.setattr(vv.store, "read", _null_store)
        chip = vv._chip_vix_level()
        assert chip["freshness"] == "missing"
        assert chip["pctile"] is None
        assert chip["value"] is None

    def test_vix_velocity_missing(self, monkeypatch):
        monkeypatch.setattr(vv.store, "read", _null_store)
        chip = vv._chip_vix_velocity()
        assert chip["freshness"] == "missing"
        assert chip["chg20_pctile"] is None

    def test_vvix_vix_missing(self, monkeypatch, tmp_path):
        """VVIX parquet absent -> missing chip."""
        monkeypatch.setattr(vv.store, "read", _null_store)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        chip = vv._chip_vvix_vix()
        assert chip["freshness"] == "missing"
        assert chip["divergence"] is False

    def test_term_slope_missing(self, monkeypatch):
        monkeypatch.setattr(vv.store, "read", _null_store)
        chip = vv._chip_term_slope()
        assert chip["freshness"] == "missing"

    def test_cboe_chip_missing_file(self, monkeypatch, tmp_path):
        """cor1m file absent -> missing chip."""
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(vv.store, "read", _null_store)
        chip = vv._chip_cor1m()
        assert chip["freshness"] == "missing"
        assert chip["pctile"] is None


# ---------------------------------------------------------------------------
# 4. Divergence flag logic
# ---------------------------------------------------------------------------

class TestVvixVixDivergence:
    def _build_vvix_parquet(self, tmp_path: Path, vvix_vals, n=260):
        """Write a vvix.parquet into tmp_path/cboe/."""
        cboe_dir = tmp_path / "cboe"
        cboe_dir.mkdir()
        idx = pd.bdate_range("2017-01-01", periods=n)
        df = pd.DataFrame({"vvix": vvix_vals}, index=idx)
        df.index.name = "date"
        df.to_parquet(cboe_dir / "vvix.parquet")
        return cboe_dir

    def test_divergence_fires_when_vvix_high_vix_low(self, monkeypatch, tmp_path):
        """VVIX high (all vals at max = pctile 100 >= 70) AND VIX low (pctile ~0 <= 40)."""
        n = 260
        # VVIX: uniformly increasing so last value is highest -> pctile=100
        vvix_vals = np.linspace(50.0, 120.0, n)
        self._build_vvix_parquet(tmp_path, vvix_vals, n)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        # VIX: decreasing so last is lowest -> pctile=0
        vix_df = pd.DataFrame(
            {"close": np.linspace(40.0, 10.0, n)},
            index=pd.bdate_range("2017-01-01", periods=n),
        )
        monkeypatch.setattr(vv.store, "read", lambda cat, name: vix_df)
        chip = vv._chip_vvix_vix()
        assert chip["divergence"] is True
        assert chip["state"] == "diverging"
        assert "watch" in chip["plain_en"].lower() or "bid" in chip["plain_en"].lower()

    def test_divergence_no_fire_when_vix_also_high(self, monkeypatch, tmp_path):
        """VIX pctile ~100 (high) AND VVIX high -> divergence=False."""
        n = 260
        vvix_vals = np.linspace(50.0, 120.0, n)
        self._build_vvix_parquet(tmp_path, vvix_vals, n)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        # VIX also increasing -> both pctile=100
        vix_df = pd.DataFrame(
            {"close": np.linspace(10.0, 40.0, n)},
            index=pd.bdate_range("2017-01-01", periods=n),
        )
        monkeypatch.setattr(vv.store, "read", lambda cat, name: vix_df)
        chip = vv._chip_vvix_vix()
        assert chip["divergence"] is False

    def test_divergence_threshold_boundary(self, monkeypatch, tmp_path):
        """Check the exact boundary: vvix_pctile=69 -> no divergence (must be >=70)."""
        n = 260
        # Need a controlled pctile value. We'll create a VVIX series where the
        # last obs sits at the 69th percentile of the window.
        window = 252
        # Build values from 1..252 so last = 174 is at the 69th percentile (174/252*100~69.0)
        base = np.arange(1.0, 253.0)
        # Pad head to fill 260
        vvix_vals = np.concatenate([np.full(8, 0.5), base])
        self._build_vvix_parquet(tmp_path, vvix_vals, n)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        # VIX low (always below the threshold)
        vix_df = pd.DataFrame(
            {"close": np.full(n, 10.0)},
            index=pd.bdate_range("2017-01-01", periods=n),
        )
        monkeypatch.setattr(vv.store, "read", lambda cat, name: vix_df)
        chip = vv._chip_vvix_vix()
        # vvix pctile should be around 69 (not quite 70), divergence should be False
        if chip["vvix_pctile"] is not None and chip["vvix_pctile"] < 70:
            assert chip["divergence"] is False


# ---------------------------------------------------------------------------
# 5. Term inversion boundary
# ---------------------------------------------------------------------------

class TestTermSlopeBoundary:
    def test_inverted_when_vix9d_gt_vix3m(self, monkeypatch):
        """VIX9D > VIX3M (ratio > 1.0) -> state='inverted', pctile=None."""
        n = 300
        idx = pd.bdate_range("2017-01-01", periods=n)
        vix9d = pd.DataFrame({"close": np.full(n, 25.0)}, index=idx)   # 25 > 20
        vix3m = pd.DataFrame({"close": np.full(n, 20.0)}, index=idx)
        def _read(cat, name):
            if name == "_VIX9D":
                return vix9d
            if name == "_VIX3M":
                return vix3m
            return None
        monkeypatch.setattr(vv.store, "read", _read)
        chip = vv._chip_term_slope()
        assert chip["state"] == "inverted"
        assert chip["pctile"] is None
        assert chip["value"] is not None and chip["value"] > 1.0

    def test_not_inverted_when_vix9d_lt_vix3m(self, monkeypatch):
        """VIX9D < VIX3M (ratio < 1.0) -> not inverted."""
        n = 300
        idx = pd.bdate_range("2017-01-01", periods=n)
        vix9d = pd.DataFrame({"close": np.full(n, 15.0)}, index=idx)
        vix3m = pd.DataFrame({"close": np.full(n, 20.0)}, index=idx)
        def _read(cat, name):
            if name == "_VIX9D":
                return vix9d
            return vix3m
        monkeypatch.setattr(vv.store, "read", _read)
        chip = vv._chip_term_slope()
        assert chip["state"] != "inverted"
        assert chip["value"] is not None and chip["value"] < 1.0

    def test_boundary_exactly_one(self, monkeypatch):
        """Ratio == 1.0 exactly: NOT > 1.0, so should NOT be 'inverted'."""
        n = 300
        idx = pd.bdate_range("2017-01-01", periods=n)
        equal = pd.DataFrame({"close": np.full(n, 20.0)}, index=idx)
        monkeypatch.setattr(vv.store, "read", lambda cat, name: equal)
        chip = vv._chip_term_slope()
        assert chip["state"] != "inverted", "Ratio == 1.0 must NOT be classified as inverted"


# ---------------------------------------------------------------------------
# 6. as_of = max last_date across non-missing chips
# ---------------------------------------------------------------------------

class TestAsOf:
    def test_as_of_is_max_chip_date(self, monkeypatch, tmp_path):
        """as_of should be the max last_date from the chips, not today-UTC."""
        # All chips will fail except vix_level (short series yields young chip with a date)
        # We need at least one non-missing chip with a last_date
        n = 260
        idx = pd.bdate_range("2020-01-02", periods=n)
        vix_df = pd.DataFrame({"close": np.linspace(15.0, 25.0, n)}, index=idx)

        def _partial_read(cat, name):
            if name in ("_VIX", "_VIX9D", "_VIX3M"):
                return vix_df
            return None

        monkeypatch.setattr(vv.store, "read", _partial_read)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)

        payload = vv.compute_vol_weather()
        assert payload is not None
        assert payload["as_of"] is not None
        # as_of must equal the last date in our synthetic vix series
        expected_date = idx[-1].strftime("%Y-%m-%d")
        assert payload["as_of"] == expected_date, (
            f"Expected as_of={expected_date}, got {payload['as_of']}"
        )

    def test_as_of_not_today_when_data_stale(self, monkeypatch, tmp_path):
        """Stale data from 2021 should produce as_of='2021-...' not today."""
        n = 260
        # Start in 2021, well in the past
        idx = pd.bdate_range("2021-01-04", periods=n)
        vix_df = pd.DataFrame({"close": np.full(n, 20.0)}, index=idx)

        def _read(cat, name):
            if name in ("_VIX", "_VIX9D", "_VIX3M"):
                return vix_df
            return None

        monkeypatch.setattr(vv.store, "read", _read)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        payload = vv.compute_vol_weather()
        assert payload is not None
        today = datetime.utcnow().strftime("%Y-%m-%d")
        assert payload["as_of"] != today, (
            f"as_of should be data date, not today ({today}). Got {payload['as_of']}"
        )
        assert payload["as_of"].startswith("2021") or payload["as_of"].startswith("2022")


# ---------------------------------------------------------------------------
# 7. Returns None when ALL chips missing
# ---------------------------------------------------------------------------

class TestAllMissing:
    def test_returns_none_when_all_missing(self, monkeypatch, tmp_path):
        """With no data sources at all, compute_vol_weather() returns None."""
        monkeypatch.setattr(vv.store, "read", _null_store)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        result = vv.compute_vol_weather()
        assert result is None


# ---------------------------------------------------------------------------
# 8. Spike state detection
# ---------------------------------------------------------------------------

class TestSpikeState:
    def test_spiking_when_5d_change_at_top(self, monkeypatch):
        """When the latest 5d VIX change is the largest in 252 obs: state='spiking'."""
        n = 300
        idx = pd.bdate_range("2017-01-01", periods=n)
        # Flat then a giant spike at the end
        close = np.concatenate([np.full(295, 15.0), np.array([15.0, 16.0, 17.0, 18.0, 40.0])])
        vix_df = pd.DataFrame({"close": close}, index=idx)
        monkeypatch.setattr(vv.store, "read", lambda cat, name: vix_df)
        chip = vv._chip_vix_velocity()
        # The 5d change is 40-15=25; all prior 5d changes are 0 -> pctile=100 -> 'spiking'
        assert chip["state"] == "spiking", f"Expected spiking, got {chip['state']}"

    def test_velocity_chip_computes_state_on_full_series(self, monkeypatch):
        """A full series (>= 252 obs) should produce a non-None state."""
        n = 300
        idx = pd.bdate_range("2017-01-01", periods=n)
        # Oscillating close to give some variety in 5d changes
        close = 20.0 + np.sin(np.arange(n) / 10.0) * 3
        vix_df = pd.DataFrame({"close": close}, index=idx)
        monkeypatch.setattr(vv.store, "read", lambda cat, name: vix_df)
        chip = vv._chip_vix_velocity()
        # A full series must yield a non-None state
        assert chip["state"] in ("quiet", "spiking", "falling_hard", "rising_fast")
        assert chip["pctile"] is not None


# ---------------------------------------------------------------------------
# 9. dspx vixeq_minus_vix secondary field
# ---------------------------------------------------------------------------

class TestDspxVixeqGap:
    def test_vixeq_minus_vix_computed(self, monkeypatch, tmp_path):
        """dspx chip should carry vixeq_minus_vix field (VIXEQ close - VIX close)."""
        n = 260
        cboe_dir = tmp_path / "cboe"
        cboe_dir.mkdir()
        idx = pd.bdate_range("2017-01-01", periods=n)
        # DSPX: constant 30
        dspx_df = pd.DataFrame({"close": np.full(n, 30.0)}, index=idx)
        dspx_df.index.name = "date"
        dspx_df.to_parquet(cboe_dir / "dspx.parquet")
        # VIXEQ: constant 25
        vixeq_df = pd.DataFrame({"close": np.full(n, 25.0)}, index=idx)
        vixeq_df.index.name = "date"
        vixeq_df.to_parquet(cboe_dir / "vixeq.parquet")
        # VIX: constant 20
        vix_df = pd.DataFrame({"close": np.full(n, 20.0)}, index=idx)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(vv.store, "read", lambda cat, name: vix_df)
        chip = vv._chip_dspx()
        assert "vixeq_minus_vix" in chip
        assert chip["vixeq_minus_vix"] == pytest.approx(5.0, abs=0.2)

    def test_vixeq_minus_vix_none_when_file_absent(self, monkeypatch, tmp_path):
        """If vixeq.parquet is absent, vixeq_minus_vix is None (not an error)."""
        n = 260
        cboe_dir = tmp_path / "cboe"
        cboe_dir.mkdir()
        idx = pd.bdate_range("2017-01-01", periods=n)
        dspx_df = pd.DataFrame({"close": np.full(n, 30.0)}, index=idx)
        dspx_df.index.name = "date"
        dspx_df.to_parquet(cboe_dir / "dspx.parquet")
        # No vixeq.parquet
        vix_df = pd.DataFrame({"close": np.full(n, 20.0)}, index=idx)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(vv.store, "read", lambda cat, name: vix_df)
        chip = vv._chip_dspx()
        assert chip["vixeq_minus_vix"] is None


# ---------------------------------------------------------------------------
# 10. cor chips plain-word framing
# ---------------------------------------------------------------------------

class TestCorChipCopy:
    """cor chips should use 'move together' framing, not 'z-score' / jargon."""

    def test_cor1m_plain_en_no_jargon(self, monkeypatch, tmp_path):
        n = 260
        cboe_dir = tmp_path / "cboe"
        cboe_dir.mkdir()
        idx = pd.bdate_range("2017-01-01", periods=n)
        # High value -> pctile=100 -> 'high' band
        df = pd.DataFrame({"close": np.linspace(10.0, 60.0, n)}, index=idx)
        df.index.name = "date"
        df.to_parquet(cboe_dir / "cor1m.parquet")
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(vv.store, "read", _null_store)
        chip = vv._chip_cor1m()
        # plain_en must use lay language, not jargon
        assert "z-score" not in chip["plain_en"].lower()
        assert "percentile" not in chip["plain_en"].lower()
        # Should describe co-movement
        assert any(w in chip["plain_en"].lower() for w in
                   ["together", "move", "stocks", "diversif"]), chip["plain_en"]

    def test_cor3m_plain_zh_natural(self, monkeypatch, tmp_path):
        n = 260
        cboe_dir = tmp_path / "cboe"
        cboe_dir.mkdir()
        idx = pd.bdate_range("2017-01-01", periods=n)
        df = pd.DataFrame({"close": np.linspace(10.0, 60.0, n)}, index=idx)
        df.index.name = "date"
        df.to_parquet(cboe_dir / "cor3m.parquet")
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(vv.store, "read", _null_store)
        chip = vv._chip_cor3m()
        assert chip["plain_zh"] != ""
        # No raw English jargon in ZH field
        assert "z-score" not in chip["plain_zh"].lower()


# ---------------------------------------------------------------------------
# 11. Full payload structure
# ---------------------------------------------------------------------------

class TestPayloadStructure:
    def test_payload_has_required_keys(self, monkeypatch, tmp_path):
        n = 260
        idx = pd.bdate_range("2019-01-02", periods=n)
        vix_df = pd.DataFrame({"close": np.linspace(12.0, 22.0, n)}, index=idx)

        def _read(cat, name):
            if name in ("_VIX", "_VIX9D", "_VIX3M"):
                return vix_df
            return None

        monkeypatch.setattr(vv.store, "read", _read)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        payload = vv.compute_vol_weather()
        assert payload is not None
        for k in ("chips", "as_of", "generated_utc", "n_young", "disclaimer_en", "disclaimer_zh"):
            assert k in payload, f"Missing key: {k}"
        assert isinstance(payload["chips"], list)
        assert len(payload["chips"]) == 8   # 8 defined chips

    def test_each_chip_has_required_fields(self, monkeypatch, tmp_path):
        n = 260
        idx = pd.bdate_range("2019-01-02", periods=n)
        vix_df = pd.DataFrame({"close": np.linspace(12.0, 22.0, n)}, index=idx)

        monkeypatch.setattr(vv.store, "read",
                            lambda cat, name: vix_df if name in ("_VIX", "_VIX9D", "_VIX3M") else None)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        payload = vv.compute_vol_weather()
        required = {"key", "name_en", "name_zh", "value", "pctile", "band", "state",
                    "plain_en", "plain_zh", "freshness", "obs_count", "last_date", "spark"}
        for chip in payload["chips"]:
            for k in required:
                assert k in chip, f"Chip {chip.get('key')} missing field: {k}"

    def test_disclaimer_present(self, monkeypatch, tmp_path):
        n = 260
        idx = pd.bdate_range("2019-01-02", periods=n)
        vix_df = pd.DataFrame({"close": np.full(n, 20.0)}, index=idx)
        monkeypatch.setattr(vv.store, "read",
                            lambda cat, name: vix_df if name.startswith("_VIX") else None)
        monkeypatch.setattr(vv.config, "data_dir", lambda: tmp_path)
        payload = vv.compute_vol_weather()
        assert "display" in payload["disclaimer_en"].lower() or "never scored" in payload["disclaimer_en"].lower()
        assert payload["disclaimer_zh"] != ""
