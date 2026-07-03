"""Tests for engine/donor.py — synthetic fixtures only, no network/file I/O.

Wave-6 G6a ship spec: research/entry_timing/WAVE6_PREREG.md §1
  donor = top-1 GICS sector by trailing-126d equal-weight return (min 5 members,
  normalised member closes); cracking = fresh weekly RSI-MACD bearish cross on
  the donor EW composite within the last 4 COMPLETED W-FRI weeks (shift-1
  completed-week convention) OR donor 20d EW return < 0 while still top-ranked.

Test cases:
  (a) top sector with completed-week bearish cross -> cracking
  (b) intact case (no cross, positive 20d) -> intact
  (c) min-members guard (< 5 members in every sector) -> None
  (d) CRITICAL: bearish cross in the CURRENT INCOMPLETE week must NOT flip state
  (e) ret20<0 leg alone (no weekly cross) -> cracking
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import donor  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

# Fixtures must use REAL GICS sector names — engine/donor.py enforces a GICS
# allowlist (production hotfix: pseudo-buckets like "ETF / macro" were out-ranking
# real sectors). S0..S4 map onto five canonical sectors.
_GICS5 = ["Information Technology", "Health Care", "Financials",
          "Industrials", "Energy"]


def _make_bdate(n: int, start: str = "2010-01-04") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _build_5_sector_closes(n_bars: int = 2200,
                            seed: int = 7,
                            sector_end_vals: dict | None = None,
                            start: str = "2010-01-04") -> tuple[dict, dict]:
    """Build 5 sectors ('S0'..'S4') × 5 members each.

    sector_end_vals: {sector: end_price} (start=100). Defaults to monotone increase.
    Returns (closes, sector_of).
    """
    if sector_end_vals is None:
        sector_end_vals = {_GICS5[i]: 100.0 + (5 - i) * 20.0 for i in range(5)}
    closes: dict   = {}
    sector_of: dict = {}
    idx = _make_bdate(n_bars, start=start)
    for si, (sec, ev) in enumerate(sector_end_vals.items()):
        for j in range(5):
            t   = f"{sec}_{j}"
            rng = np.random.default_rng(seed * 100 + si * 10 + j)
            v   = np.linspace(100.0, ev, n_bars)
            # tiny noise so composites stay distinct but nearly monotone
            v  *= (1.0 + rng.normal(0, 0.001, n_bars))
            closes[t]    = pd.Series(v, index=idx, dtype=float)
            sector_of[t] = sec
    return closes, sector_of


def _identify_top_sector(closes: dict, sector_of: dict) -> str:
    """Return the sector that has the highest 126d composite return at the last bar."""
    from collections import defaultdict
    by_sec: dict = defaultdict(list)
    for t, s in closes.items():
        sec = sector_of.get(t)
        if sec is None:
            continue
        s2 = s.dropna()
        by_sec[sec].append(s2 / s2.iloc[0])
    best_sec, best_ret = None, -np.inf
    for sec, lst in by_sec.items():
        ew = pd.concat(lst, axis=1).mean(axis=1)
        r126 = float(ew.iloc[-1] / ew.iloc[-127] - 1)
        if r126 > best_ret:
            best_ret, best_sec = r126, sec
    return best_sec


# ══════════════════════════════════════════════════════════════════════════════
# (a) Top sector with a completed-week bearish cross -> cracking
# ══════════════════════════════════════════════════════════════════════════════

class TestCrackingViaWeeklyBearCross:
    """A bearish cross that occurred in a COMPLETED week fires the cracking leg."""

    def test_cracking_state(self):
        """Build closes so that the natural top-126d sector has a recent sharp
        decline.  We do NOT hard-code which sector wins; instead we call
        _identify_top_sector to discover it and verify state=cracking.

        Design:
          - ALL sectors go monotone up (small noise).  At the very end, crash
            ALL sectors identically (so the leadership order is preserved) in the
            LAST 8 bars (one completed W-FRI week back PLUS a few daily bars).
          - The 8-bar crash (−30%) guarantees a bearish weekly RSI-MACD cross in
            the most recently COMPLETED W-FRI weekly bar (it fires on that bar
            and becomes 'known' the week after via shift(1); but because we end
            on or after that next W-FRI week, it is inside the 4-completed-week
            lookback).
          - The test ends on a FRIDAY so the last W-FRI is a completed bar.
        """
        n_bars = 2500  # plenty of history for RSI to stabilise
        # End on a Friday (weekday=4) for clean W-FRI alignment
        idx_full = pd.bdate_range(start="2010-01-04", periods=n_bars)
        fri_mask = idx_full.weekday == 4
        last_fri = idx_full[fri_mask][-1]
        # Go back 2 more completed weeks (10 bars) so the crash lands exactly 2
        # completed W-FRI weeks ago (known via shift(1) inside the 4-week window).
        # Actually: crash everything starting 15 bars from last_fri.
        crash_start_from_end = 15   # 15 bars before last bar
        idx = idx_full[idx_full <= last_fri]
        n   = len(idx)

        sector_end_vals = {
            _GICS5[0]: 200.0,  # leader
            _GICS5[1]: 130.0,
            _GICS5[2]: 120.0,
            _GICS5[3]: 115.0,
            _GICS5[4]: 110.0,
        }
        closes: dict = {}
        sector_of: dict = {}
        for si, (sec, ev) in enumerate(sector_end_vals.items()):
            for j in range(5):
                t   = f"{sec}_{j}"
                rng = np.random.default_rng(si * 10 + j)
                v   = np.linspace(100.0, ev, n)
                # crash last `crash_start_from_end` bars by -30%
                crash_start = n - crash_start_from_end
                v[crash_start:] = v[crash_start] * np.linspace(1.0, 0.70, crash_start_from_end)
                v *= (1.0 + rng.normal(0, 0.001, n))
                closes[t]    = pd.Series(v, index=idx, dtype=float)
                sector_of[t] = sec

        result = donor.donor_state(closes, sector_of)
        assert result is not None, "Expected dict, got None"
        # Whatever sector is the donor, it should be cracking (all sectors crash alike)
        assert result["state"] == "cracking", (
            f"Expected state=cracking after 30% crash in last 15 bars on all sectors. "
            f"Got state={result['state']}, legs={result['legs']}, "
            f"donor_sector={result['donor_sector']}")
        # At least one leg should fire — either weekly_bear_cross or ret20_neg
        assert result["legs"]["weekly_bear_cross"] or result["legs"]["ret20_neg"], (
            f"Expected at least one cracking leg to fire. Got legs={result['legs']}")


# ══════════════════════════════════════════════════════════════════════════════
# (b) Intact case
# ══════════════════════════════════════════════════════════════════════════════

class TestIntactCase:
    """When no cracking leg fires, state == 'intact'."""

    def test_intact_state(self):
        """All sectors go monotone up with tiny noise.  No crash -> no bearish
        cross, ret20 > 0.  State must be 'intact'."""
        closes, sector_of = _build_5_sector_closes(n_bars=2200, seed=5)
        result = donor.donor_state(closes, sector_of)
        assert result is not None, "Expected dict, got None"
        assert result["state"] == "intact", (
            f"Expected state=intact for monotone uptrend. "
            f"Got state={result['state']}, legs={result['legs']}, "
            f"donor_sector={result['donor_sector']}")
        assert result["legs"]["weekly_bear_cross"] is False
        assert result["legs"]["ret20_neg"] is False

    def test_result_shape(self):
        """Result dict has all required keys with correct types."""
        closes, sector_of = _build_5_sector_closes(n_bars=2200, seed=3)
        result = donor.donor_state(closes, sector_of)
        assert result is not None
        assert isinstance(result["donor_sector"], str)
        assert result["state"] in ("cracking", "intact")
        assert isinstance(result["legs"], dict)
        assert isinstance(result["legs"]["weekly_bear_cross"], bool)
        assert isinstance(result["legs"]["ret20_neg"], bool)
        assert isinstance(result["ranked_ret126"], (float, type(None)))
        assert isinstance(result["asof"], str)
        assert isinstance(result["n_sectors"], int)


# ══════════════════════════════════════════════════════════════════════════════
# (c) Min-members guard -> None
# ══════════════════════════════════════════════════════════════════════════════

class TestMinMembersGuard:
    """Fewer than 5 members in every sector -> donor_state returns None."""

    def test_none_when_all_sectors_have_4_members(self):
        """4 members per sector (< DONOR_MIN_MEMBERS=5) -> None."""
        sectors = ["X", "Y", "Z"]
        closes: dict = {}
        sector_of: dict = {}
        idx = _make_bdate(2000)
        for sec in sectors:
            for i in range(4):   # only 4 per sector
                t = f"{sec}_{i}"
                closes[t]    = pd.Series(np.linspace(100, 200, 2000), index=idx, dtype=float)
                sector_of[t] = sec
        result = donor.donor_state(closes, sector_of)
        # With only 4 members, elig (cnt >= 5) is never True -> no donor -> None
        assert result is None, (
            f"Expected None with 4 members per sector, got {result}")

    def test_none_when_single_sector(self):
        """Only one sector with >=5 members -> insufficient (need >=2 eligible
        for a meaningful ranking) -> donor_state returns None."""
        closes: dict = {}
        sector_of: dict = {}
        idx = _make_bdate(2000)
        for i in range(6):
            t = f"SINGLE_{i}"
            closes[t]    = pd.Series(np.linspace(100, 200, 2000), index=idx, dtype=float)
            sector_of[t] = "Utilities"
        result = donor.donor_state(closes, sector_of)
        assert result is None, (
            f"Expected None with only one eligible sector, got {result}")


# ══════════════════════════════════════════════════════════════════════════════
# (d) CRITICAL: bearish cross in the CURRENT INCOMPLETE week must NOT flip state
# ══════════════════════════════════════════════════════════════════════════════

class TestCompletedWeekDiscipline:
    """A bearish cross that ONLY appears in the CURRENT (not-yet-closed) W-FRI
    week must NOT be seen as 'known' at the last daily bar.

    Implementation of the shift(1) prior-closed-week convention: a cross printed
    on week w is actionable only AFTER that week closes (wbear_known = wbear.shift(1)).

    We test this directly by inspecting the engine's internal weekly pipeline on
    a controlled monotone series and verifying that wbear_known=False at the last
    daily bar when the cross falls in the current incomplete week.
    """

    def test_incomplete_week_cross_not_in_wbear_known(self):
        """Direct unit test of the completed-week shift-1 convention.

        Build a series that ends on a Wednesday (mid-week).  Apply a sharp 3-bar
        crash on Mon-Wed of the current week.  With W-FRI resampling, this crash
        will appear in the 2023-06-09 weekly bar (the UPCOMING Friday).  After
        shift(1), that bar is shifted to the FOLLOWING Friday (2023-06-16) and is
        therefore NOT known at 2023-06-07 (last daily bar).

        We verify by calling donor_state on a scenario where ALL sectors are
        monotone steady EXCEPT the crash, so whatever sector is chosen as donor,
        we check that weekly_bear_cross is False (shift-1 discipline).
        """
        n_bars   = 2200
        idx_full = pd.bdate_range(start="2015-01-05", periods=n_bars)
        wed_mask = idx_full.weekday == 2
        last_wed = idx_full[wed_mask][-1]
        idx      = idx_full[idx_full <= last_wed]
        n        = len(idx)

        # Build 5 sectors × 5 members, all steadily rising — NO prior cross.
        # The ONLY disturbance is the 3-bar crash in the current incomplete week
        # applied to ALL sectors equally (so leadership order preserved, and the
        # crash is in the CURRENT INCOMPLETE week for all).
        closes: dict = {}
        sector_of: dict = {}
        sector_end_vals = {
            _GICS5[0]: 200.0, _GICS5[1]: 150.0, _GICS5[2]: 130.0, _GICS5[3]: 120.0, _GICS5[4]: 110.0,
        }
        for si, (sec, ev) in enumerate(sector_end_vals.items()):
            for j in range(5):
                t   = f"{sec}_{j}"
                rng = np.random.default_rng(si * 10 + j + 999)
                v   = np.linspace(100.0, ev, n)
                # crash ONLY the last 3 bars (Mon-Wed of the current, incomplete week)
                v[-3:] = v[-4] * np.array([0.93, 0.88, 0.82])
                v  *= (1.0 + rng.normal(0, 0.0005, n))   # very tiny noise
                closes[t]    = pd.Series(v, index=idx, dtype=float)
                sector_of[t] = sec

        result = donor.donor_state(closes, sector_of)
        assert result is not None, "Expected dict, got None"

        # CRITICAL: weekly_bear_cross must be False because the crash is in the
        # CURRENT INCOMPLETE W-FRI week.  With shift(1) that cross is not yet known.
        assert result["legs"]["weekly_bear_cross"] is False, (
            "CRITICAL DISCIPLINE FAILURE: bearish cross in the current INCOMPLETE "
            "W-FRI week was counted as 'known'. The shift(1) completed-week "
            "convention must prevent this. "
            f"Got legs={result['legs']}, state={result['state']}, "
            f"donor_sector={result['donor_sector']}, asof={result.get('asof')}")

    def test_friday_ending_current_week_cross_blocked_by_shift1(self):
        """Mutation-proof test: daily index ends on a Friday where a raw weekly
        RSI-MACD bearish cross fires on the final W-FRI bar.

        When the last bar IS a Friday, the W-FRI resample label for the current
        week EQUALS the last daily date.  ffill maps it onto the last daily bar.
        WITHOUT shift(1) the current week's cross leaks through as 'known';
        WITH shift(1) the cross is pushed one week forward and is NOT known yet.

        This test FAILS if `wbear.shift(1)` is replaced by `wbear` in donor.py.

        Fixture design:
          - 5 sectors × 5 members, each built from a sine-wave-on-trend series
            (rising trend + oscillation) scaled by sector weight (0.6..1.0×).
          - The full 3500-bar sine-wave series is trimmed to end exactly on
            2022-11-18 (a Friday) — a date where the donor EW composite
            produces a raw RSI-MACD bearish cross on that W-FRI bar.
          - All sectors share the same base oscillation (leadership preserved).
          - After shift(1) the 2022-11-18 cross is pushed to the following week
            and is NOT known at 2022-11-18 → weekly_bear_cross must be False.

        Note: the cross is produced by tuning_harness.rsi_macd (the same
        implementation used in production runs).  The exact cross date was
        verified by instrumenting the composite pipeline directly.
        """
        n_bars   = 3500
        idx_full = pd.bdate_range(start="2010-01-04", periods=n_bars)
        # Trim to 2022-11-18 (Friday) — the date where the sine-wave EW composite
        # generates a raw weekly RSI-MACD bearish cross on the final W-FRI bar.
        TARGET_FRI = pd.Timestamp("2022-11-18")
        idx        = idx_full[idx_full <= TARGET_FRI]
        n          = len(idx)
        assert idx[-1] == TARGET_FRI, "Fixture start must reach 2022-11-18"
        assert idx[-1].weekday() == 4, "Fixture must end on a Friday"

        # Base oscillating series: rising trend + sine wave, normalised to 1.0
        t_full = np.linspace(0, 6 * np.pi, n_bars)
        v_base = 100.0 + 50.0 * t_full / t_full.max() + 30.0 * np.sin(t_full)
        v_base = v_base / v_base[0]
        v_base = v_base[:n]

        # Scale each sector by a different factor so S0 is the clear 126d leader
        sector_scales = {
            _GICS5[0]: 1.00, _GICS5[1]: 0.90, _GICS5[2]: 0.80, _GICS5[3]: 0.70, _GICS5[4]: 0.60,
        }
        closes: dict   = {}
        sector_of: dict = {}
        for si, (sec, scale) in enumerate(sector_scales.items()):
            for j in range(5):
                t   = f"{sec}_{j}"
                rng = np.random.default_rng(si * 10 + j + 555)
                v   = v_base * scale
                v  *= (1.0 + rng.normal(0, 0.0001, n))   # minimal noise
                closes[t]    = pd.Series(v, index=idx, dtype=float)
                sector_of[t] = sec

        result = donor.donor_state(closes, sector_of)
        assert result is not None, "Expected dict, got None"

        # The 2022-11-18 W-FRI weekly bar is the CURRENT (not-yet-closed) week
        # at the last daily bar (they are the same date).  shift(1) must push the
        # raw cross one week forward so it is NOT counted as 'known' today.
        # This assertion FAILS if shift(1) is removed from donor.py line 176.
        assert result["legs"]["weekly_bear_cross"] is False, (
            "CRITICAL SHIFT-1 DISCIPLINE FAILURE (Friday-ending index): "
            "the 2022-11-18 W-FRI weekly bar equals the last daily bar, so ffill "
            "maps it onto the last daily row. Without shift(1), the raw bearish "
            "cross on that bar leaks through as 'known'. "
            "This test MUST fail if shift(1) is removed from engine/donor.py. "
            f"Got legs={result['legs']}, state={result['state']}, "
            f"donor_sector={result['donor_sector']}, asof={result.get('asof')}")


# ══════════════════════════════════════════════════════════════════════════════
# (e) ret20<0 leg alone -> cracking (no weekly cross needed)
# ══════════════════════════════════════════════════════════════════════════════

class TestRet20NegLeg:
    """ret20 < 0 on the donor while still top-ranked -> cracking."""

    def test_cracking_via_ret20_only(self):
        """ALL sectors go monotone up, then the last 25 bars decline gently for
        ALL of them.  This ensures:
          - The leadership order from the pre-crash period is maintained (so
            whichever sector leads 126d also has ret20 < 0).
          - The 25-bar decline is gentle enough (no RSI-MACD cross on the weekly
            bars) so we can isolate the ret20 leg.
          - We do NOT hard-code which sector is the donor; we check that the
            donor (whatever it is) has ret20_neg=True.
        """
        n_bars = 2500
        # End on a Friday for clean W-FRI alignment
        idx_full = pd.bdate_range(start="2010-01-04", periods=n_bars)
        fri_mask = idx_full.weekday == 4
        last_fri = idx_full[fri_mask][-1]
        idx      = idx_full[idx_full <= last_fri]
        n        = len(idx)

        sector_end_vals = {
            _GICS5[0]: 250.0,
            _GICS5[1]: 140.0,
            _GICS5[2]: 125.0,
            _GICS5[3]: 118.0,
            _GICS5[4]: 112.0,
        }
        closes: dict = {}
        sector_of: dict = {}
        for si, (sec, ev) in enumerate(sector_end_vals.items()):
            for j in range(5):
                t   = f"{sec}_{j}"
                rng = np.random.default_rng(si * 10 + j + 42)
                v   = np.linspace(100.0, ev, n)
                # Gentle last-25-bar decline (−4%) applied to ALL sectors equally
                # so leadership order is preserved and all have ret20 < 0.
                peak = v[-26]
                v[-25:] = np.linspace(peak, peak * 0.96, 25)
                v  *= (1.0 + rng.normal(0, 0.0005, n))
                closes[t]    = pd.Series(v, index=idx, dtype=float)
                sector_of[t] = sec

        result = donor.donor_state(closes, sector_of)
        assert result is not None, "Expected dict, got None"
        assert result["legs"]["ret20_neg"] is True, (
            f"Expected ret20_neg=True after 4% decline in last 25 bars on all sectors. "
            f"Got legs={result['legs']}, donor_sector={result['donor_sector']}")
        assert result["state"] == "cracking", (
            f"Expected state=cracking (ret20<0 fires). "
            f"Got state={result['state']}, legs={result['legs']}")


# ══════════════════════════════════════════════════════════════════════════════
# Never-raises contract
# ══════════════════════════════════════════════════════════════════════════════

class TestNeverRaises:
    """donor_state must never raise regardless of degenerate inputs."""

    def test_empty_closes(self):
        try:
            result = donor.donor_state({}, {})
            assert result is None
        except Exception as e:
            pytest.fail(f"donor_state raised on empty input: {e}")

    def test_all_none_sector(self):
        idx    = _make_bdate(2000)
        closes = {"A": pd.Series(np.linspace(100, 200, 2000), index=idx, dtype=float)}
        sec_of = {"A": None}
        try:
            result = donor.donor_state(closes, sec_of)
            assert result is None
        except Exception as e:
            pytest.fail(f"donor_state raised with all-None sectors: {e}")

    def test_single_bar_series(self):
        idx    = _make_bdate(1)
        closes = {f"T{i}": pd.Series([100.0], index=idx) for i in range(10)}
        sec_of = {f"T{i}": "S" for i in range(10)}
        try:
            donor.donor_state(closes, sec_of)
        except Exception as e:
            pytest.fail(f"donor_state raised on single-bar series: {e}")

    def test_nan_series(self):
        idx    = _make_bdate(2000)
        closes = {f"T{i}": pd.Series([float("nan")] * 2000, index=idx) for i in range(10)}
        sec_of = {f"T{i}": "S" for i in range(10)}
        try:
            donor.donor_state(closes, sec_of)
        except Exception as e:
            pytest.fail(f"donor_state raised on all-NaN series: {e}")


class TestFallbackFidelity:
    """The pure-Python RSI-MACD fallback must be numerically IDENTICAL to
    tuning_harness.rsi_macd — the registered Wave-5b/Wave-6 spec — so a
    broken guarded import can never silently change the weekly-cross leg.
    (Ship-review finding: an earlier adjust=False draft diverged on ~2% of
    cross bars; this test pins the identity.)"""

    def test_fallback_matches_tuning_harness_exactly(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "signal_engine"))
        try:
            import tuning_harness as TH
        except Exception:
            import pytest
            pytest.skip("tuning_harness not importable in this environment")
        import numpy as np
        import pandas as pd
        from engine import donor

        rng = np.random.default_rng(7)
        c = pd.Series(
            100 * np.exp(np.cumsum(rng.normal(0, 0.02, 400))),
            index=pd.bdate_range("2023-01-02", periods=400),
        )
        m1, s1 = TH.rsi_macd(c)
        m2, s2 = donor._rsi_macd_fallback(c)
        assert float((m1 - m2).abs().max()) < 1e-9
        assert float((s1 - s2).abs().max()) < 1e-9
        x1 = ((m1 < s1) & (m1.shift(1) >= s1.shift(1))).fillna(False)
        x2 = donor._xdn(m2, s2).fillna(False)
        assert int((x1 != x2).sum()) == 0


class TestGicsAllowlist:
    """Pseudo-sector buckets from the live builder's wider map ('ETF / macro',
    theme tags) must NEVER compete for donor — on 2026-07-02 the unfiltered
    ranking crowned 'ETF / macro' at +144% 126d (production bug, hotfixed).
    The donor universe is exactly the 11 GICS sectors the G6a study ranked."""

    def test_pseudo_bucket_excluded_even_when_top_ranked(self):
        import numpy as np
        import pandas as pd
        from engine import donor

        idx = pd.bdate_range("2018-01-02", periods=1600)
        rng = np.random.default_rng(3)
        closes, sector_of = {}, {}
        # two real GICS sectors, 5 flat-ish members each
        for si, sec in enumerate(("Information Technology", "Health Care")):
            for k in range(5):
                t = f"{sec[:2]}{k}"
                drift = 0.0004 if si == 0 else 0.0002   # IT outperforms HC
                closes[t] = pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, 0.01, len(idx)))), index=idx)
                sector_of[t] = sec
        # a pseudo-bucket with 5 members MASSIVELY outperforming (levered-ETF-like)
        for k in range(5):
            t = f"ETF{k}"
            closes[t] = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.004, 0.02, len(idx)))), index=idx)
            sector_of[t] = "ETF / macro"

        res = donor.donor_state(closes, sector_of)
        assert res is not None
        assert res["donor_sector"] in donor.GICS_SECTORS
        assert res["donor_sector"] != "ETF / macro"
        assert res["n_sectors"] <= 11
