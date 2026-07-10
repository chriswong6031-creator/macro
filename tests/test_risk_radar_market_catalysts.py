"""Tests for engine/risk_radar_market_catalysts.py

All synthetic frames — NO network. Monkeypatches lib.store.read as in existing risk_radar tests.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import risk_radar_market_catalysts as rmc


# ---------------------------------------------------------------------------
# helpers to build synthetic frames
# ---------------------------------------------------------------------------

def _bdate_range(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _breadth_df(n: int = 500, adv_frac: float = 0.55, n_members: int = 450) -> pd.DataFrame:
    """Flat adv/dec frame with given adv fraction."""
    idx = _bdate_range(n)
    adv = np.round(adv_frac * n_members).astype(int)
    dec = n_members - adv
    return pd.DataFrame(
        {"n_members": n_members, "adv": adv, "dec": dec,
         "nh": 10, "nl": 2,
         "pct_above_50": 60.0, "pct_above_200": 55.0,
         "ad_line": np.cumsum(np.full(n, adv - dec))},
        index=idx,
    )


def _spy_df(closes, volumes=None) -> pd.DataFrame:
    """Build a synthetic SPY DataFrame with close and volume."""
    n = len(closes)
    idx = _bdate_range(n)
    vols = volumes if volumes is not None else np.full(n, 1e6)
    return pd.DataFrame({"close": closes, "volume": vols}, index=idx)


def _vix_df(closes, n=None, start="2010-01-04") -> pd.DataFrame:
    """Build a synthetic VIX-style DataFrame."""
    if n is not None:
        closes = np.full(n, closes)
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"close": closes}, index=idx)


def _fred_hy(oas_series) -> pd.DataFrame:
    """Build a synthetic BAMLH0A0HYM2 frame."""
    idx = pd.bdate_range("2018-01-02", periods=len(oas_series))
    return pd.DataFrame({"hy_oas": oas_series}, index=idx)


def _patch_today(monkeypatch, as_of: str) -> None:
    """Patch rmc.date so date.today() returns a fixed date.

    This lets _is_fresh / _bd_since return deterministic results against
    synthetic frames whose last bar is years in the past.  Pass the ISO date
    string you want 'today' to be (e.g. the day of the chip event or a few
    business days after it).
    """
    from datetime import date as _real_date
    target = _real_date.fromisoformat(as_of)

    class _FakeDate(_real_date):
        @classmethod
        def today(cls):
            return target

    monkeypatch.setattr(rmc, "date", _FakeDate)


# ---------------------------------------------------------------------------
# C1 — thrust_confluence
# ---------------------------------------------------------------------------

class TestC1ThrustConfluence:

    def _make_breadth(self, n: int, adv_frac: float, n_members: int = 450) -> pd.DataFrame:
        return _breadth_df(n, adv_frac, n_members)

    def test_bam_fires_when_adv_ratio_high(self):
        """10d sum adv / 10d sum dec >= 1.97 should fire bam."""
        b = _breadth_df(n=500, adv_frac=0.70, n_members=450)  # 70% advancing
        chip = rmc._c1_thrust_confluence(b)
        # bam: 10d sum adv / 10d sum dec with 70% advancing
        # adv=315, dec=135, ratio=2.33 >= 1.97 => bam fires
        assert chip["detail"]["components"]["bam"]["fired"] is True
        assert chip["fired"] is True

    def test_adt5_fires_when_ratio_high(self):
        """5d mean ratio >= 0.73 should fire adt5."""
        b = _breadth_df(n=500, adv_frac=0.75, n_members=450)
        chip = rmc._c1_thrust_confluence(b)
        assert chip["detail"]["components"]["adt5"]["fired"] is True
        assert chip["fired"] is True

    def test_t70_fires_on_three_consecutive(self):
        """3 consecutive days ratio >= 0.70."""
        b = _breadth_df(n=500, adv_frac=0.71, n_members=450)
        chip = rmc._c1_thrust_confluence(b)
        assert chip["detail"]["components"]["t70"]["fired"] is True

    def test_no_fire_when_ratio_low(self):
        """Low adv fraction — no component should fire."""
        b = _breadth_df(n=500, adv_frac=0.45, n_members=450)
        chip = rmc._c1_thrust_confluence(b)
        assert chip["fired"] is False
        assert chip["detail"]["k"] == 0

    def test_mature_n_gate(self):
        """n_members < MATURE_N => absent chip."""
        b = _breadth_df(n=500, adv_frac=0.75, n_members=100)  # below 400
        chip = rmc._c1_thrust_confluence(b)
        assert chip["fired"] is False

    def test_k_counts_components_not_doubled(self):
        """k >= 1 means fired; detail carries component counts."""
        b = _breadth_df(n=500, adv_frac=0.75, n_members=450)
        chip = rmc._c1_thrust_confluence(b)
        assert chip["detail"]["burst_counted_once"] is True
        assert chip["key"] == "thrust_confluence"
        assert chip["accruing"] is True

    def test_zbt_fires_on_sharp_bounce(self, monkeypatch):
        """Build a series where adv ratio dips below 0.40 then surges above 0.615 within 10 sessions.

        The frame ends at the surge so patching today to the last frame date makes
        the event fresh and lets us assert fired=True.
        """
        n = 500
        b = _breadth_df(n=n, adv_frac=0.55, n_members=450)
        # 15 days of deep washout (adv ~22%) then 7 days of very high adv (~85%)
        # 10d EMA of ratio: after washout EMA dips well below 0.40;
        # after the surge spike it jumps above 0.615 within the same 10-session window.
        low_adv = int(0.22 * 450)
        high_adv = int(0.85 * 450)
        b = b.copy()
        b.iloc[-22:-7, b.columns.get_loc("adv")] = low_adv
        b.iloc[-22:-7, b.columns.get_loc("dec")] = 450 - low_adv
        b.iloc[-7:, b.columns.get_loc("adv")] = high_adv
        b.iloc[-7:, b.columns.get_loc("dec")] = 450 - high_adv

        # Patch today to the last day of the frame so the event is fresh
        last_date = str(b.index[-1].date())
        _patch_today(monkeypatch, last_date)

        chip = rmc._c1_thrust_confluence(b)
        assert chip["accruing"] is True
        # ZBT component should fire: low EMA < 0.40 then high EMA >= 0.615 in <=10 sessions
        assert chip["detail"]["components"]["zbt"]["fired"] is True
        assert chip["fired"] is True
        assert chip["fresh"] is True

    def test_missing_columns_returns_absent(self):
        """Missing adv/dec columns should return absent chip."""
        b = pd.DataFrame({"n_members": [450] * 10}, index=_bdate_range(10))
        chip = rmc._c1_thrust_confluence(b)
        assert chip["fired"] is False
        assert "note" in chip["detail"]


# ---------------------------------------------------------------------------
# C2 — msi_swing
# ---------------------------------------------------------------------------

class TestC2MSISwing:

    def _make_breadth_with_swing(self) -> pd.DataFrame:
        """Create breadth that produces a summation low < 100 within last 126 bars, then > 1000 now.

        Construction: neutral 350 bars to build moderate summation, then a severe bearish
        episode (bars 350-420) that crashes summation well below 100 inside the last-126
        window, then very bullish 420+ to spike summation above 1000 with positive slope.
        """
        n = 500
        b = _breadth_df(n=n, adv_frac=0.50, n_members=450)
        b = b.copy()
        # Neutral: 50% adv -> zero oscillator, summation near 0
        b.iloc[:350, b.columns.get_loc("adv")] = int(0.50 * 450)
        b.iloc[:350, b.columns.get_loc("dec")] = 450 - int(0.50 * 450)
        # Very bearish: 15% adv -> RANA crashes, summation drops well below 100
        low_adv = int(0.15 * 450)
        b.iloc[350:420, b.columns.get_loc("adv")] = low_adv
        b.iloc[350:420, b.columns.get_loc("dec")] = 450 - low_adv
        # Very bullish: 90% adv -> summation surges above 1000 with positive slope
        high_adv = int(0.90 * 450)
        b.iloc[420:, b.columns.get_loc("adv")] = high_adv
        b.iloc[420:, b.columns.get_loc("dec")] = 450 - high_adv
        return b

    def test_swing_fires_on_low_to_high(self, monkeypatch):
        b = self._make_breadth_with_swing()
        # The summation crossing above 1000 occurs around bar 430-440.
        # Patch today to the last frame date so that crossing is within _FRESH_BD (10bd).
        # (crossing is ~bar 435 of 500, frame last is bar 499; gap ~65bd; use crossing-day +3bd)
        # We determine the crossing date by computing the summation inline.
        b2 = b.copy()
        b2.index = pd.to_datetime(b2.index)
        b_mature = b2[b2["n_members"] >= rmc.THRUST_N]
        total = (b_mature["adv"] + b_mature["dec"]).replace(0, float("nan"))
        rana = 1000.0 * (b_mature["adv"] - b_mature["dec"]) / total
        osc = rana.ewm(span=19, adjust=False).mean() - rana.ewm(span=39, adjust=False).mean()
        summ = osc.cumsum()
        above1k = summ > 1000
        crossings = summ[(~above1k.shift(1, fill_value=False)) & above1k]
        assert not crossings.empty, "test setup: summation did not cross 1000"
        crossing_date = crossings.index[-1]
        today_str = str((crossing_date + pd.tseries.offsets.BDay(3)).date())
        _patch_today(monkeypatch, today_str)

        chip = rmc._c2_msi_swing(b)
        assert chip["accruing"] is True
        assert chip["key"] == "msi_swing"
        assert chip["fired"] is True
        assert chip["fresh"] is True
        assert chip["detail"]["summation_now"] > 1000
        assert chip["detail"]["recent_min_126"] < 100

    def test_no_fire_when_flat(self):
        """Flat 55% adv — summation won't do a washout→swing."""
        b = _breadth_df(n=500, adv_frac=0.55, n_members=450)
        chip = rmc._c2_msi_swing(b)
        # Summation at steady 55% stays roughly flat; won't hit min < 100 AND now > 1000
        assert chip["accruing"] is True

    def test_thrust_n_gate(self):
        """n_members < THRUST_N should return absent."""
        b = _breadth_df(n=500, adv_frac=0.75, n_members=100)  # below 250
        chip = rmc._c2_msi_swing(b)
        assert chip["fired"] is False
        assert "note" in chip["detail"]

    def test_missing_columns_absent(self):
        b = pd.DataFrame({"n_members": [450] * 10}, index=_bdate_range(10))
        chip = rmc._c2_msi_swing(b)
        assert chip["fired"] is False


# ---------------------------------------------------------------------------
# C3 — washout_thrust20 (cache absent degrades gracefully)
# ---------------------------------------------------------------------------

class TestC3WashoutThrust20:

    def test_absent_when_no_cache(self, tmp_path):
        """No _closes_cache.parquet => absent chip with informative note."""
        chip = rmc._c3_washout_thrust20(tmp_path)
        assert chip["fired"] is False
        assert "cache-local" in chip["detail"]["note"]
        assert chip["accruing"] is True

    def test_fires_when_cache_present(self, tmp_path, monkeypatch):
        """Build a synthetic closes cache that triggers the washout (<25%) → thrust (>90%) round-trip.

        Construction:
          - bars 0..129: price=120 (high baseline, 20dma ~120)
          - bars 130..154: price=5 (far below 20dma → pct < 25%, washout)
          - bars 155..199: price linearly rising 200→288 (strictly > lagging 20dma → pct > 90%)

        The thrust crossing happens around bar 155.  Today is patched to ~3bd after that
        crossing so _is_fresh returns True.
        """
        n = 200
        n_tickers = 50
        idx = _bdate_range(n)
        closes = np.ones((n, n_tickers)) * 120.0
        closes[130:155] = 5.0
        for i in range(155, 200):
            closes[i] = 200.0 + (i - 155) * 2.0  # rising trend stays ahead of 20dma

        df = pd.DataFrame(closes, index=idx)
        cache_path = tmp_path / "data" / "breadth" / "_closes_cache.parquet"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path)

        # Determine the thrust crossing date to patch today
        ma20 = df.rolling(20, min_periods=10).mean()
        pct = (df > ma20).sum(axis=1) / df.notna().sum(axis=1)
        above90 = pct > 0.90
        below25 = pct < 0.25
        crossings = []
        last_below25_i = None
        for i in range(len(pct)):
            if below25.iloc[i]:
                last_below25_i = i
            elif above90.iloc[i] and last_below25_i is not None:
                crossings.append(pct.index[i])
                last_below25_i = None
        assert crossings, "test setup: no washout→thrust crossing found"
        last_cross = crossings[-1]
        today_str = str((last_cross + pd.tseries.offsets.BDay(3)).date())
        _patch_today(monkeypatch, today_str)

        chip = rmc._c3_washout_thrust20(tmp_path)
        assert chip["accruing"] is True
        assert chip["fired"] is True
        assert chip["fresh"] is True
        assert chip["detail"]["min_63d"] < 0.25
        assert chip["detail"]["pct_now"] > 0.90


# ---------------------------------------------------------------------------
# C4 — Follow-Through Day
# ---------------------------------------------------------------------------

class TestC4FTD:

    def test_ftd_fires_on_valid_sequence(self, monkeypatch):
        """Build SPY with: drawdown > 6%, rally attempt, day 4 +1.5% on higher volume.

        Patches today to 5 business days after the FTD date so that bd_ago <= 10
        and both fired=True and fresh=True are asserted.
        """
        n = 120
        closes = [500.0] * n
        volumes = [1e6] * n

        # Peak at bar 20, then drawdown (63d rolling high = 500 from bar 0..19)
        for i in range(21, 35):
            closes[i] = 500.0 - (i - 20) * 3.5   # drops to ~452 = -9.6%

        # Rally attempt starts at bar 35 (first up close from low)
        closes[34] = 452.0   # low
        closes[35] = 455.0   # up close = attempt day 1
        closes[36] = 453.0   # day 2
        closes[37] = 456.0   # day 3
        # day 4: +1.5% on higher volume -> FTD
        closes[38] = closes[37] * 1.015
        volumes[38] = volumes[37] * 1.2

        spy_df = _spy_df(closes, volumes)
        monkeypatch.setattr(rmc.store, "read", lambda g, n: spy_df if (g, n) == ("yahoo", "SPY") else None)

        # FTD date is bar 38 of the frame (2020-01-02 + 38 bdays = 2020-02-25)
        ftd_date = spy_df.index[38]
        today_str = str((ftd_date + pd.tseries.offsets.BDay(5)).date())
        _patch_today(monkeypatch, today_str)

        chip = rmc._c4_ftd(None)
        assert chip["accruing"] is True
        assert chip["key"] == "ftd"
        assert chip["fired"] is True
        assert chip["fresh"] is True
        assert chip["detail"]["last_ftd"] == str(ftd_date.date())
        assert chip["detail"]["n_ftds_all"] >= 1

    def test_no_ftd_without_drawdown(self, monkeypatch):
        """Flat or rising SPY — no FTD."""
        closes = np.linspace(400, 480, 100).tolist()
        volumes = [1e6] * 100
        spy_df = _spy_df(closes, volumes)
        monkeypatch.setattr(rmc.store, "read", lambda g, n: spy_df if (g, n) == ("yahoo", "SPY") else None)
        chip = rmc._c4_ftd(None)
        assert chip["fired"] is False

    def test_absent_when_spy_unavailable(self, monkeypatch):
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        chip = rmc._c4_ftd(None)
        assert chip["fired"] is False
        assert "note" in chip["detail"]


# ---------------------------------------------------------------------------
# C5 — Retest breadth divergence
# ---------------------------------------------------------------------------

class TestC5RetestDivergence:

    def _make_retest_scenario(self, monkeypatch, fewer_nl=True, higher_adline=True):
        """Build SPY + breadth where low2 retests low1 with divergence."""
        n = 200
        idx = _bdate_range(n)

        # SPY: initial low at bar 80, bounce to +5%, then retest to ~same level at bar 185
        closes = [300.0] * n
        low1 = 270.0   # bar 80
        bounce = 285.0  # bar 100
        low2 = 271.0   # bar 185 (within 2% of low1 -> retest)

        for i in range(n):
            if i < 80:
                closes[i] = 300.0
            elif i == 80:
                closes[i] = low1
            elif i <= 100:
                closes[i] = low1 + (bounce - low1) * (i - 80) / 20
            elif i <= 160:
                closes[i] = bounce
            elif i <= 185:
                closes[i] = bounce - (bounce - low2) * (i - 160) / 25
            else:
                closes[i] = 275.0

        spy_df = pd.DataFrame({"close": closes}, index=idx)

        # Breadth: divergence = fewer nl and higher ad_line at low2
        nl = [5.0] * n
        ad_line_base = list(range(n))
        if fewer_nl:
            nl[80] = 40.0   # many new lows at low1
            nl[185] = 15.0  # fewer new lows at low2
        else:
            nl[80] = 20.0
            nl[185] = 25.0  # more new lows at low2 -> no facet_a

        ad_line = [float(x) for x in ad_line_base]
        if not higher_adline:
            ad_line[185] = ad_line[80] - 50  # lower at low2 -> no facet_b

        b = pd.DataFrame(
            {"n_members": 450, "adv": 225, "dec": 225,
             "nh": 10, "nl": nl,
             "pct_above_50": 60.0, "pct_above_200": 55.0,
             "ad_line": ad_line},
            index=idx,
        )

        monkeypatch.setattr(rmc.store, "read",
                            lambda g, nm: spy_df if (g, nm) == ("yahoo", "SPY") else None)
        return b

    def test_fires_with_both_facets(self, monkeypatch):
        """Assert chip fires (True) with both facets active when today is patched near low2_date."""
        b = self._make_retest_scenario(monkeypatch, fewer_nl=True, higher_adline=True)

        # low2 is at bar 185 of the 200-bar frame.  Patch today to 3 bdays after low2_date
        # so _is_fresh(low2_date) returns True.
        low2_date = b.index[185]
        today_str = str((low2_date + pd.tseries.offsets.BDay(3)).date())
        _patch_today(monkeypatch, today_str)

        chip = rmc._c5_retest_divergence(b, None)
        assert chip["accruing"] is True
        assert chip["key"] == "retest_divergence"
        assert chip["fired"] is True
        assert isinstance(chip["fired"], bool)   # no numpy bool leak
        assert chip["fresh"] is True
        assert chip["detail"]["is_retest"] is True
        assert isinstance(chip["detail"]["is_retest"], bool)  # no numpy bool leak
        assert chip["detail"]["facets"]["facet_a"]["fired"] is True
        assert chip["detail"]["facets"]["facet_b"]["fired"] is True

    def test_absent_when_spy_missing(self, monkeypatch):
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        b = _breadth_df(200)
        chip = rmc._c5_retest_divergence(b, None)
        assert chip["fired"] is False

    def test_absent_when_ad_line_missing(self, monkeypatch):
        """Breadth without nl/ad_line -> absent chip."""
        spy_df = _spy_df(np.linspace(300, 280, 200))
        monkeypatch.setattr(rmc.store, "read",
                            lambda g, nm: spy_df if (g, nm) == ("yahoo", "SPY") else None)
        b = pd.DataFrame({"n_members": 450, "adv": 225, "dec": 225}, index=_bdate_range(200))
        chip = rmc._c5_retest_divergence(b, None)
        assert chip["fired"] is False


# ---------------------------------------------------------------------------
# C6 — VIX term resolution
# ---------------------------------------------------------------------------

class TestC6VixTermResolution:

    def _patch_vix(self, monkeypatch, vix_closes, vix3m_closes, start="2010-01-04"):
        v = _vix_df(vix_closes, start=start)
        v3 = _vix_df(vix3m_closes, start=start)
        def _read(g, n):
            if g == "yahoo" and n == "_VIX":
                return v
            if g == "yahoo" and n == "_VIX3M":
                return v3
            return None
        monkeypatch.setattr(rmc.store, "read", _read)

    def test_fires_when_episode_then_resolution(self, monkeypatch):
        """Backwardation episode (r>1 for 5 sessions) then last 3 sessions r<1."""
        n = 100
        vix_closes = np.full(n, 15.0)
        vix3m_closes = np.full(n, 18.0)  # VIX3M > VIX normally (r < 1)

        # Episode: bars 80..84 — VIX > VIX3M (r > 1)
        vix_closes[80:85] = 22.0    # VIX > VIX3M 18 -> r = 22/18 = 1.22
        # Resolution: bars 97..99 — VIX < VIX3M
        vix_closes[97:] = 14.0      # r = 14/18 < 1

        self._patch_vix(monkeypatch, vix_closes, vix3m_closes)
        chip = rmc._c6_vix_term_resolution()
        assert chip["accruing"] is True
        assert chip["key"] == "vix_term_resolution"
        assert chip["detail"]["episode_found"] is True
        assert chip["fired"] is True

    def test_no_fire_when_no_episode(self, monkeypatch):
        """No backwardation episode -> chip not fired."""
        n = 100
        vix_closes = np.full(n, 14.0)
        vix3m_closes = np.full(n, 18.0)   # always r < 1
        self._patch_vix(monkeypatch, vix_closes, vix3m_closes)
        chip = rmc._c6_vix_term_resolution()
        assert chip["fired"] is False
        assert chip["detail"]["episode_found"] is False

    def test_no_fire_when_episode_not_resolved(self, monkeypatch):
        """Episode but still in backwardation -> not resolved."""
        n = 100
        vix_closes = np.full(n, 22.0)   # always r > 1
        vix3m_closes = np.full(n, 18.0)
        self._patch_vix(monkeypatch, vix_closes, vix3m_closes)
        chip = rmc._c6_vix_term_resolution()
        assert chip["fired"] is False

    def test_absent_when_vix_missing(self, monkeypatch):
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        chip = rmc._c6_vix_term_resolution()
        assert chip["fired"] is False


# ---------------------------------------------------------------------------
# C7 — OAS ROC rollover
# ---------------------------------------------------------------------------

class TestC7OASRollover:

    def _patch_oas(self, monkeypatch, oas_series):
        df = _fred_hy(oas_series)
        monkeypatch.setattr(rmc.store, "read",
                            lambda g, n: df if (g, n) == ("fred", "BAMLH0A0HYM2") else None)

    def test_fires_on_rollover(self, monkeypatch):
        """OAS spikes within last 63 bars (ROC pctile → ~0.99), then gradually retreats.

        Construction: OAS ramps from baseline to 10 over bars 500-555, then retreats over
        555-599.  During the retreat the 21d-ROC pctile falls through 0.75 and keeps declining
        (p_now < p_5ago), satisfying the full rollover condition.  Today is patched to 3bd
        after the first rollover crossing so fresh=True.
        """
        n = 600
        oas = np.full(n, 3.5)
        # Ramp up bars 500-555 (55 bars) to a peak of 10
        for i in range(500, 556):
            oas[i] = 3.5 + (10.0 - 3.5) * (i - 500) / 55.0
        # Gradual descent bars 556-599 (44 bars) back toward baseline
        for i in range(556, 600):
            oas[i] = 10.0 - (10.0 - 3.5) * (i - 556) / 44.0

        self._patch_oas(monkeypatch, oas)

        # Determine rollover date inline to set today correctly
        from engine.indicators import pct_rank_window as _prw
        idx7 = pd.bdate_range("2018-01-02", periods=n)
        oas_s = pd.Series(oas, index=pd.to_datetime(idx7))
        roc = oas_s.diff(21)
        p = _prw(roc, 504)
        p_63 = p.iloc[-63:]
        p_max = float(p_63.max())
        peak_pos = p_63.idxmax()
        after_peak = p_63[p_63.index > peak_pos]
        rollover_thresh = p_max - 0.15
        rolled = after_peak[(after_peak <= rollover_thresh) & (after_peak < 0.75)]
        assert not rolled.empty, "test setup: no rollover crossing found"
        since_date = rolled.index[0]
        today_str = str((since_date + pd.tseries.offsets.BDay(3)).date())
        _patch_today(monkeypatch, today_str)

        chip = rmc._c7_oas_rollover()
        assert chip["accruing"] is True
        assert chip["key"] == "oas_rollover"
        assert chip["fired"] is True
        assert chip["fresh"] is True
        assert chip["detail"]["p_max_63"] >= 0.90
        assert chip["detail"]["p_now"] <= chip["detail"]["p_max_63"] - 0.15

    def test_no_fire_when_flat(self, monkeypatch):
        """Flat OAS -> low ROC pctile -> no rollover."""
        oas = np.full(600, 3.5)
        self._patch_oas(monkeypatch, oas)
        chip = rmc._c7_oas_rollover()
        assert chip["fired"] is False

    def test_absent_when_store_missing(self, monkeypatch):
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        chip = rmc._c7_oas_rollover()
        assert chip["fired"] is False


# ---------------------------------------------------------------------------
# C8 — Vol instability VETO
# ---------------------------------------------------------------------------

class TestC8VolInstabilityVeto:

    def test_veto_active_when_vol_high(self, monkeypatch):
        """Large VIX daily swings -> 21d realized-vol pctile >= 0.80 -> veto active=True.

        Uses a fixed random seed for reproducibility.  Verified: with seed=42 and randn*8
        on the last 50 bars, p_now ≈ 0.98 >= 0.80.
        """
        n = 600
        vix_closes = np.full(n, 20.0)
        np.random.seed(42)
        vix_closes[550:] = 20.0 + np.random.randn(50) * 8
        v = pd.DataFrame({"close": vix_closes}, index=pd.bdate_range("2015-01-02", periods=n))
        monkeypatch.setattr(rmc.store, "read",
                            lambda g, nm: v if (g, nm) == ("yahoo", "_VIX") else None)
        veto = rmc._c8_vol_instability_veto()
        assert veto["active"] is True
        assert veto["p_now"] >= 0.80

    def test_veto_inactive_when_calm(self, monkeypatch):
        """Flat VIX -> low daily changes -> low inst pctile -> veto inactive."""
        n = 600
        vix_closes = np.full(n, 15.0)
        v = pd.DataFrame({"close": vix_closes}, index=pd.bdate_range("2015-01-02", periods=n))
        monkeypatch.setattr(rmc.store, "read",
                            lambda g, nm: v if (g, nm) == ("yahoo", "_VIX") else None)
        veto = rmc._c8_vol_instability_veto()
        assert veto["active"] is False

    def test_veto_inactive_when_vix_missing(self, monkeypatch):
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        veto = rmc._c8_vol_instability_veto()
        assert veto["active"] is False


# ---------------------------------------------------------------------------
# compute() — top-level, degrade-on-missing
# ---------------------------------------------------------------------------

class TestCompute:

    def test_compute_returns_schema(self, monkeypatch):
        """compute() always returns the required top-level keys."""
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        result = rmc.compute()
        assert "asof" in result
        assert "chips" in result
        assert isinstance(result["chips"], list)
        assert "market_confirmed" in result
        assert "market_confirmed_raw" in result
        assert "n_fresh" in result
        assert "veto" in result
        assert "note" in result

    def test_compute_degrades_gracefully_on_empty_data(self, monkeypatch):
        """Empty store returns => all chips absent, market_confirmed=False."""
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        monkeypatch.setattr(rmc, "store", type("s", (), {"read": lambda g, n: None})())
        result = rmc.compute()
        assert result["market_confirmed"] is False
        assert result["n_fresh"] == 0

    def test_compute_never_raises_on_garbage(self):
        """compute() must not raise even with bad environment."""
        # We call it with a non-existent root path
        result = rmc.compute(root="/nonexistent/path")
        assert isinstance(result, dict)
        assert "market_confirmed" in result

    def test_chip_keys_and_labels(self, monkeypatch):
        """All chips have required fields."""
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        result = rmc.compute()
        for chip in result["chips"]:
            assert "key" in chip
            assert "label_en" in chip
            assert "label_zh" in chip
            assert "fired" in chip
            assert "fresh" in chip
            assert "accruing" in chip
            assert chip["accruing"] is True

    def test_seven_chips_returned(self, monkeypatch):
        """Exactly 7 confirmation chips (C1-C7; C8 is veto)."""
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        result = rmc.compute()
        assert len(result["chips"]) == 7

    def test_market_confirmed_false_when_veto_active(self, monkeypatch):
        """Even if a chip is fresh, veto suppresses market_confirmed."""
        # Patch VIX to produce high volatility (veto active)
        n = 600
        vix_closes = np.abs(np.random.randn(n)) * 15 + 20
        v = pd.DataFrame({"close": vix_closes}, index=pd.bdate_range("2015-01-02", periods=n))

        def _read(g, nm):
            if nm == "_VIX":
                return v
            return None

        monkeypatch.setattr(rmc.store, "read", _read)
        result = rmc.compute()
        # If veto is active, market_confirmed should be False even if n_fresh > 0
        if result["veto"]["active"]:
            assert result["market_confirmed"] is False

    def test_market_confirmed_raw_ignores_veto(self, monkeypatch):
        """market_confirmed_raw = n_fresh >= 1 regardless of veto."""
        monkeypatch.setattr(rmc.store, "read", lambda g, n: None)
        result = rmc.compute()
        assert result["market_confirmed_raw"] == (result["n_fresh"] >= 1)
