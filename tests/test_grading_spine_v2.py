"""Tests for engine.grading — Outcome Spine v2 primitives (W0.1a).

Covers the W0.1a additions to engine/grading.py:
  1. fwd_mfe_H  — max favorable excursion in forward_metrics
  2. terminal_state() — per-fire partition: STOPPED / DEAD_MONEY / CUSHIONED / CLEAN_LIFTOFF
     with the two named liftoff parameterizations (clean15_126, clean8_21)
  3. cushion_incidence() — cumulative incidence with stop-out as competing risk; NEVER a
     median over reachers (§1.1 ban)
  4. as_of_panel() PIT membership wiring via sp1500_pit_membership.parquet

Synthetic price paths are hand-crafted so the expected outcome is provable by inspection,
not computed by calling the function under test.

Spec authority: research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md §1.1, §5.1 sub-task 1.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import grading
from engine.grading import (
    TerminalState,
    terminal_state,
    cushion_incidence,
    STOP_BARRIER,
    CUSHION_BARRIER,
    LIFTOFF_15,
    LIFTOFF_8,
    LIFTOFF_HORIZON_126,
    LIFTOFF_HORIZON_21,
    DEAD_MONEY_BAND,
    DEAD_MONEY_CAP,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _bseries(vals, start="2020-01-01"):
    """Business-day Series from a list of floats."""
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series([float(v) for v in vals], index=idx)


def _flat_series(entry, *, length=200, signal_offset=0):
    """Series that stays flat at ``entry`` for ``length`` bars.
    Signal date is at ``signal_offset`` (0-based), fill at signal_offset+1."""
    vals = [entry] * length
    return _bseries(vals)


def _descent_then_stop(entry, signal_offset=1, length=150):
    """Price drops 5.1% within the first 10 bars after fill → STOPPED."""
    vals = [entry] * length
    fill = signal_offset + 1
    for k in range(fill + 1, fill + 8):
        vals[k] = entry * 0.948  # below STOP_BARRIER=0.95
    return _bseries(vals)


def _cushion_no_liftoff(entry, cushion_bar=5, signal_offset=1, length=150):
    """Price hits +5.1% at cushion_bar but never reaches +15%."""
    vals = [entry] * length
    fill = signal_offset + 1
    vals[fill + cushion_bar] = entry * 1.055  # above CUSHION_BARRIER but below LIFTOFF_15
    return _bseries(vals)


def _liftoff_clean15(entry, lift_bar=30, signal_offset=1, length=200):
    """Price hits +16% at lift_bar (no stop) → CLEAN_LIFTOFF for clean15_126."""
    vals = [entry] * length
    fill = signal_offset + 1
    # Ensure cushion is crossed too
    vals[fill + lift_bar] = entry * 1.16
    return _bseries(vals)


def _liftoff_clean8(entry, lift_bar=10, signal_offset=1, length=150):
    """Price hits +9% at lift_bar within 21d → CLEAN_LIFTOFF for clean8_21."""
    vals = [entry] * length
    fill = signal_offset + 1
    vals[fill + lift_bar] = entry * 1.09
    return _bseries(vals)


# --------------------------------------------------------------------------- #
# 1. fwd_mfe_H — present in forward_metrics, mirrors fwd_mdd_H
# --------------------------------------------------------------------------- #
class TestFwdMfe:
    def test_fwd_mfe_is_present_and_nonnegative(self):
        s = _bseries([100, 101, 110, 105, 108, 115, 112])
        sig = str(s.index[1].date())   # fill = bar 2 (price 110)
        m = grading.forward_metrics(s, sig, horizons=(4,))
        assert f"fwd_mfe_4" in m
        assert m["fwd_mfe_4"] is not None
        assert m["fwd_mfe_4"] >= 0.0

    def test_fwd_mfe_max_of_forward_window(self):
        # fill at bar 1 (price 100); forward bars 2,3,4 are 90, 120, 110
        s = _bseries([100, 100, 90, 120, 110, 105])
        sig = str(s.index[0].date())   # signal bar 0 -> fill bar 1 (price 100)
        m = grading.forward_metrics(s, sig, horizons=(3,))
        # MFE = max(90,120,110)/100 - 1 = 0.20
        assert m["fwd_mfe_3"] == pytest.approx(0.20)

    def test_fwd_mfe_zero_when_always_below_entry(self):
        # All forward bars below entry price
        s = _bseries([100, 100, 95, 93, 90, 88])
        sig = str(s.index[0].date())   # fill bar 1 (price 100)
        m = grading.forward_metrics(s, sig, horizons=(3,))
        assert m["fwd_mfe_3"] == 0.0   # max(0, negative) = 0

    def test_fwd_mfe_strictly_forward_excludes_fill_bar(self):
        # Fill bar (bar 1) is the local maximum; forward bars are all below it.
        s = _bseries([90, 120, 95, 96, 97, 98])  # bar 1 = 120 (the fill)
        sig = str(s.index[0].date())
        m = grading.forward_metrics(s, sig, horizons=(3,))
        assert m["entry_price"] == 120.0
        # Forward window is bars 2,3,4 (95,96,97) — all below 120
        assert m["fwd_mfe_3"] == 0.0     # fill bar excluded

    def test_fwd_mfe_none_when_not_matured(self):
        s = _bseries(range(100, 105))   # only 5 bars
        sig = str(s.index[0].date())
        m = grading.forward_metrics(s, sig, horizons=(60,))
        assert m["fwd_mfe_60"] is None

    def test_fwd_mdd_and_fwd_mfe_both_present_same_call(self):
        s = _bseries([100, 100, 80, 110, 105, 95])
        sig = str(s.index[0].date())
        m = grading.forward_metrics(s, sig, horizons=(3,))
        # mdd = min(80,110,105)/100 - 1 = -0.20; mfe = max(80,110,105)/100-1 = 0.10
        assert m["fwd_mdd_3"] == pytest.approx(-0.20)
        assert m["fwd_mfe_3"] == pytest.approx(0.10)

    def test_parity_fwd_mfe_absent_in_old_keys(self):
        """Parity assertion: fwd_mfe does NOT change existing fwd_ret / fwd_mdd keys."""
        s = _bseries([100, 101, 102, 103, 104, 105, 106, 107])
        sig = str(s.index[2].date())
        m = grading.forward_metrics(s, sig, horizons=(3,))
        # All existing keys present and correct
        assert m["entry_price"] == 103.0
        assert m["fwd_ret_3"] == pytest.approx(106.0 / 103.0 - 1.0)
        assert "fwd_mdd_3" in m
        assert "fwd_mfe_3" in m


# --------------------------------------------------------------------------- #
# 2. terminal_state() — per-fire partition
# --------------------------------------------------------------------------- #
class TestTerminalState:

    def test_stopped_when_stop_hits_before_cushion(self):
        """Price drops below −5% before ever reaching +5% → STOPPED."""
        entry = 100.0
        sig_bar = 1
        fill_bar = 2
        vals = [100.0] * 200
        # Drop to 94 (below 95) at bar fill+3
        vals[fill_bar + 3] = entry * 0.94
        s = _bseries(vals)
        sig = str(s.index[sig_bar].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["state"] == TerminalState.STOPPED
        assert r["stopped_at_bar"] == 3

    def test_clean_liftoff_clean15_126(self):
        """Price hits +16% before −5% within 126 bars → CLEAN_LIFTOFF (clean15_126)."""
        entry = 100.0
        sig_bar = 1
        fill_bar = 2
        vals = [entry] * 200
        vals[fill_bar + 40] = entry * 1.16   # +16%
        s = _bseries(vals)
        sig = str(s.index[sig_bar].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["state"] == TerminalState.CLEAN_LIFTOFF
        assert r["parameterization"] == "clean15_126"
        assert r["liftoff_at_bar"] == 40

    def test_clean_liftoff_clean8_21(self):
        """Price hits +9% before −5% within 21 bars → CLEAN_LIFTOFF (clean8_21)."""
        entry = 100.0
        sig_bar = 1
        fill_bar = 2
        vals = [entry] * 100
        vals[fill_bar + 10] = entry * 1.09   # +9%
        s = _bseries(vals)
        sig = str(s.index[sig_bar].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_8, liftoff_horizon=LIFTOFF_HORIZON_21)
        assert r["state"] == TerminalState.CLEAN_LIFTOFF
        assert r["parameterization"] == "clean8_21"

    def test_cushioned_hits_plus5_no_liftoff(self):
        """Price hits +5.5% but never hits +15% or −5% → CUSHIONED."""
        entry = 100.0
        sig_bar = 1
        fill_bar = 2
        vals = [entry] * 200
        vals[fill_bar + 20] = entry * 1.055   # above +5% but below +15%
        s = _bseries(vals)
        sig = str(s.index[sig_bar].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["state"] == TerminalState.CUSHIONED
        assert r["cushion_at_bar"] is not None

    def test_dead_money_never_moves_enough(self):
        """Price never moves ±8% and stays < +5% at read → DEAD_MONEY."""
        entry = 100.0
        sig_bar = 0
        fill_bar = 1
        # Price stays at 101 (flat) for 127 bars — well within ±8% band, ret < +5%
        vals = [entry] * (fill_bar + LIFTOFF_HORIZON_126 + 5)
        for k in range(fill_bar + 1, len(vals)):
            vals[k] = 101.0
        s = _bseries(vals)
        sig = str(s.index[sig_bar].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["state"] == TerminalState.DEAD_MONEY
        # entry_price = 101.0 (fill bar), read = 101.0 → ret = 0
        # BUT: fill bar is signal+1. signal_bar=0 → fill=1 (vals[1]=100.0, the original entry).
        # Forward bars start at fill+1 (vals[2..127] = 101.0). ret_at_read = 101/100 - 1 = 0.01
        assert r["ret_at_read"] == pytest.approx(101.0 / 100.0 - 1.0, abs=1e-9)

    def test_straddle_bar_stop_wins(self):
        """When stop (−5%) and cushion (+5%) would both trigger on the same bar:
        stop wins (pre-registered straddle tie rule, §1.1)."""
        # A bar where close is simultaneously ≤ stop_barrier AND ≥ cushion_barrier
        # is impossible with a single close value, but the tie rule governs the
        # sequential loop: since stop is checked first, it wins.
        # Simulate: bar fill+1 is exactly at stop_barrier (0.95*entry).
        entry = 100.0
        sig_bar = 0
        fill_bar = 1
        vals = [entry] * (fill_bar + LIFTOFF_HORIZON_126 + 5)
        vals[fill_bar + 1] = entry * STOP_BARRIER   # exactly 95.0
        # This bar also equals stop_barrier; cushion_barrier is 105 — not reached.
        # The key test: close == stop_barrier triggers STOPPED (stop wins).
        s = _bseries(vals)
        sig = str(s.index[sig_bar].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["state"] == TerminalState.STOPPED
        assert r["stopped_at_bar"] == 1

    def test_not_matured_returns_none_state(self):
        """Insufficient forward data → state=None (frozen-until-matured)."""
        s = _bseries(range(100, 130))   # only 30 bars
        sig = str(s.index[0].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["state"] is None

    def test_parameterization_label_clean15_126(self):
        s = _bseries([100.0] * 200)
        sig = str(s.index[0].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["parameterization"] == "clean15_126"

    def test_parameterization_label_clean8_21(self):
        s = _bseries([100.0] * 100)
        sig = str(s.index[0].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_8, liftoff_horizon=LIFTOFF_HORIZON_21)
        assert r["parameterization"] == "clean8_21"

    def test_entry_price_is_next_bar_close(self):
        """Entry price must be the FILL bar (next-bar), not the signal bar."""
        s = _bseries([90.0, 100.0] + [100.0] * 200)
        sig = str(s.index[0].date())   # signal bar 0 (price 90); fill bar 1 (price 100)
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["entry_price"] == 100.0

    def test_delisted_terminal_stops_before_horizon(self):
        """A series that ends before the horizon window expires resolves as not-matured."""
        s = _bseries([100.0] * 10)    # only 10 bars; horizon 126 → not matured
        sig = str(s.index[0].date())
        r = terminal_state(s, sig, liftoff_mult=LIFTOFF_15, liftoff_horizon=LIFTOFF_HORIZON_126)
        assert r["state"] is None


# --------------------------------------------------------------------------- #
# 3. cushion_incidence() — all-fires denominator, competing risk
# --------------------------------------------------------------------------- #
class TestCushionIncidence:

    def _make_fire(self, entry=100.0, *, n_bars=60, cushion_at=None, stop_at=None):
        """Build (close_series, signal_date) for one synthetic fire.

        cushion_at  — bar offset from fill at which to put price at +5.5%
        stop_at     — bar offset from fill at which to put price at -5.5%
        If neither, price stays flat at entry.
        """
        sig_offset = 1
        vals = [entry] * (n_bars + sig_offset + 2)
        fill = sig_offset + 1
        if cushion_at is not None:
            vals[fill + cushion_at] = entry * 1.055
        if stop_at is not None:
            vals[fill + stop_at] = entry * 0.945
        s = _bseries(vals)
        return (s, str(s.index[sig_offset].date()))

    def test_n_fires_and_n_gradable_counts(self):
        fires = [self._make_fire(n_bars=30) for _ in range(5)]
        r = cushion_incidence(fires, k_days=(5, 10, 21))
        assert r["n_fires"] == 5
        assert r["n_gradable"] == 5

    def test_cushion_incidence_at_k5_counts_only_by_day5(self):
        # 3 fires cushion at bar 3 (within k=5), 2 fires cushion at bar 10 (outside k=5)
        fires = (
            [self._make_fire(cushion_at=3) for _ in range(3)]
            + [self._make_fire(cushion_at=10) for _ in range(2)]
        )
        r = cushion_incidence(fires, k_days=(5,))
        ci5 = r["cumulative_incidence"][5]
        assert ci5["cushioned"] == 3
        assert ci5["at_risk"] == 5
        assert ci5["incidence_pct"] == pytest.approx(3 / 5 * 100, rel=1e-4)

    def test_stop_out_reduces_cushion_count_at_k(self):
        """A fire that stops BEFORE cushion is reached should NOT count as cushioned."""
        # 3 fires cushioned at bar 5; 2 fires stopped at bar 3 (before cushion)
        fires = (
            [self._make_fire(cushion_at=5) for _ in range(3)]
            + [self._make_fire(stop_at=3) for _ in range(2)]
        )
        r = cushion_incidence(fires, k_days=(10,))
        ci10 = r["cumulative_incidence"][10]
        # Only the 3 cushioned fires count; stopped fires do NOT count as cushioned
        assert ci10["cushioned"] == 3
        assert ci10["stopped"] == 2

    def test_denominator_is_all_fires_not_reachers(self):
        """§1.1 ban: denominator is ALL gradable fires, not just those that cushioned.
        A signal that stops all its slow fires must NOT appear better on cushion speed."""
        # 2 fires cushion at bar 5; 8 fires stop at bar 1 (the stopped fires prevent
        # the denominator-shrinkage trick)
        fires = (
            [self._make_fire(cushion_at=5) for _ in range(2)]
            + [self._make_fire(stop_at=1) for _ in range(8)]
        )
        r = cushion_incidence(fires, k_days=(10,))
        ci10 = r["cumulative_incidence"][10]
        assert ci10["at_risk"] == 10      # all fires, not just reachers
        assert ci10["cushioned"] == 2
        assert ci10["incidence_pct"] == pytest.approx(20.0, rel=1e-4)

    def test_post_cushion_breach_detected(self):
        """After a fire cushions (+5%), if price later drops back below entry,
        post_cushion_breakeven_breach_rate should be non-zero."""
        entry = 100.0
        sig_offset = 1
        n_bars = 50
        vals = [entry] * (n_bars + sig_offset + 5)
        fill = sig_offset + 1
        vals[fill + 5] = entry * 1.055   # cushion at bar 5
        vals[fill + 10] = entry * 0.99   # breach entry after cushion
        s = _bseries(vals)
        fire = (s, str(s.index[sig_offset].date()))
        r = cushion_incidence([fire], k_days=(21,))
        assert r["cushion_reached_count"] == 1
        assert r["post_cushion_breakeven_breach_rate"] == 100.0  # 1/1 breach

    def test_post_cushion_no_breach_when_price_holds(self):
        """Fire cushions but price stays above entry — no breach."""
        entry = 100.0
        sig_offset = 1
        n_bars = 50
        vals = [entry] * (n_bars + sig_offset + 5)
        fill = sig_offset + 1
        vals[fill + 5] = entry * 1.055   # cushion at bar 5
        # All subsequent bars above entry
        for k in range(fill + 6, fill + 30):
            vals[k] = entry * 1.02
        s = _bseries(vals)
        fire = (s, str(s.index[sig_offset].date()))
        r = cushion_incidence([fire], k_days=(21,))
        assert r["cushion_reached_count"] == 1
        assert r["post_cushion_breakeven_breach_rate"] == 0.0

    def test_empty_fires_returns_safe_nulls(self):
        r = cushion_incidence([], k_days=(5, 10, 21))
        assert r["n_fires"] == 0
        assert r["n_gradable"] == 0
        for k in (5, 10, 21):
            assert r["cumulative_incidence"][k]["incidence_pct"] is None

    def test_cumulative_incidence_is_monotone_in_k(self):
        """Incidence at k=21 >= k=10 >= k=5 (monotone non-decreasing)."""
        fires = [self._make_fire(cushion_at=k) for k in [2, 7, 15, 30]]
        r = cushion_incidence(fires, k_days=(5, 10, 21))
        ci = r["cumulative_incidence"]
        assert ci[5]["incidence_pct"] <= ci[10]["incidence_pct"] <= ci[21]["incidence_pct"]


# --------------------------------------------------------------------------- #
# 4. as_of_panel() PIT membership wiring
# --------------------------------------------------------------------------- #
class TestPitMembershipWiring:

    def _make_pit_parquet(self, rows, tmp_path: Path) -> str:
        """Write a synthetic sp1500_pit_membership.parquet to tmp_path."""
        df = pd.DataFrame(rows)
        df["start_date"] = pd.to_datetime(df["start_date"])
        df["end_date"] = pd.to_datetime(df["end_date"])
        p = tmp_path / "sp1500_pit_membership.parquet"
        df.to_parquet(p, index=False)
        # Clear the module-level cache so the new file is loaded
        grading._PIT_MEMBERSHIP_CACHE.update({"path": None, "df": None})
        return str(p)

    def test_pit_survivorship_tag_when_universe_history_cold(self, tmp_path):
        """Empty universe_history ledger + valid PIT file → survivorship='pit'."""
        pit_path = self._make_pit_parquet([
            {"ticker": "OLDCO", "start_date": "2000-01-01", "end_date": None, "src": "sp500"},
            {"ticker": "GONE",  "start_date": "2000-01-01", "end_date": "2012-06-01", "src": "sp500"},
        ], tmp_path)
        closes = {
            "OLDCO": pd.Series([100.0] * 200, index=pd.bdate_range("2000-01-01", periods=200)),
            "GONE":  pd.Series([50.0] * 200,  index=pd.bdate_range("2000-01-01", periods=200)),
            "NEWCO": pd.Series([10.0] * 200,  index=pd.bdate_range("2020-01-01", periods=200)),
        }
        # asof = 2005: both OLDCO and GONE were members; NEWCO was not born yet in PIT
        panel = grading.as_of_panel(
            closes, "2005-01-01",
            ledger=pd.DataFrame(),   # cold-start: empty universe_history ledger
            include_dead=False,
            pit_path=pit_path,
        )
        assert panel["survivorship"] == "pit"
        assert set(panel["members"]) == {"OLDCO", "GONE"}
        assert "NEWCO" not in panel["members"]  # PIT shows NEWCO not yet listed

    def test_pit_excludes_expired_members(self, tmp_path):
        """A name whose end_date < asof should NOT appear in the panel."""
        pit_path = self._make_pit_parquet([
            {"ticker": "ACTIVE", "start_date": "2000-01-01", "end_date": None,         "src": "sp500"},
            {"ticker": "EXPIRED","start_date": "2000-01-01", "end_date": "2010-06-01", "src": "sp500"},
        ], tmp_path)
        closes = {
            "ACTIVE":  pd.Series([100.0] * 200, index=pd.bdate_range("2000-01-01", periods=200)),
            "EXPIRED": pd.Series([80.0]  * 200, index=pd.bdate_range("2000-01-01", periods=200)),
        }
        panel = grading.as_of_panel(
            closes, "2015-01-01",
            ledger=pd.DataFrame(),
            include_dead=False,
            pit_path=pit_path,
        )
        assert panel["survivorship"] == "pit"
        assert "ACTIVE" in panel["members"]
        assert "EXPIRED" not in panel["members"]

    def test_cold_start_when_no_pit_file(self, tmp_path):
        """When both ledger and PIT file are absent → cold-start fallback."""
        closes = {"A": pd.Series([100.0] * 200, index=pd.bdate_range("2020-01-01", periods=200))}
        panel = grading.as_of_panel(
            closes, "2010-01-01",
            ledger=pd.DataFrame(),
            include_dead=False,
            pit_path=str(tmp_path / "no_such_file.parquet"),   # nonexistent
        )
        assert panel["survivorship"] == "cold-start"
        assert set(panel["members"]) == {"A"}

    def test_universe_history_ledger_takes_precedence_over_pit(self, tmp_path):
        """When universe_history has an entry for asof, PIT is NOT consulted."""
        pit_path = self._make_pit_parquet([
            {"ticker": "PIT_ONLY", "start_date": "2020-01-01", "end_date": None, "src": "sp500"},
        ], tmp_path)
        # Build a minimal universe_history ledger that covers asof
        led = pd.DataFrame([{
            "ticker": "LEDGER_MEMBER", "group": "sp500",
            "name": "LedgerMember", "sector": "Tech",
            "first_seen": pd.Timestamp("2020-01-01"),
            "last_seen":  pd.Timestamp("2026-12-31"),
            "active": True,
        }])
        closes = {
            "LEDGER_MEMBER": pd.Series([100.0] * 200, index=pd.bdate_range("2020-01-01", periods=200)),
            "PIT_ONLY":      pd.Series([50.0]  * 200, index=pd.bdate_range("2020-01-01", periods=200)),
        }
        panel = grading.as_of_panel(
            closes, "2021-06-01",
            ledger=led,
            include_dead=False,
            pit_path=pit_path,
        )
        # universe_history returned a member → "as-of" tag, not "pit"
        assert panel["survivorship"] == "as-of"
        assert "LEDGER_MEMBER" in panel["members"]
        assert "PIT_ONLY" not in panel["members"]

    def test_pit_membership_file_schema_sanity(self):
        """The actual sp1500_pit_membership.parquet in the repo is readable and has
        the expected column types."""
        from pathlib import Path
        from lib import config
        p = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
        if not p.exists():
            pytest.skip("sp1500_pit_membership.parquet not present in this environment")
        df = pd.read_parquet(p)
        assert "ticker" in df.columns
        assert "start_date" in df.columns
        assert len(df) > 0
        # Spot-check: start_dates are parseable as dates
        assert pd.to_datetime(df["start_date"]).notna().any()


# --------------------------------------------------------------------------- #
# 5. Parity assertion — existing forward_metrics outputs unchanged
# --------------------------------------------------------------------------- #
class TestParity:
    """Verify existing callers' outputs are byte-identical after W0.1a additions."""

    def test_fwd_ret_and_mdd_unchanged(self):
        """fwd_ret_H and fwd_mdd_H values must match pre-W0.1a expectations exactly."""
        s = pd.Series(
            [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
            index=pd.bdate_range("2020-01-01", periods=9),
        )
        sig = str(s.index[2].date())   # signal bar 2 (price 102); fill bar 3 (price 103)
        m = grading.forward_metrics(s, sig, horizons=(3,))
        # fwd_ret_3: close[fill+3] / entry - 1 = 106/103 - 1
        assert m["fwd_ret_3"] == pytest.approx(106.0 / 103.0 - 1.0)
        # fwd_mdd_3: min(104,105,106)/103 - 1 = 0.0 (all above entry)
        assert m["fwd_mdd_3"] == 0.0
        # fwd_mfe_3 is NEW but must not change existing values
        assert m["fwd_mfe_3"] == pytest.approx(106.0 / 103.0 - 1.0)

    def test_grade_next_bar_return_unchanged(self):
        s = pd.Series(
            [100.0, 101.0, 102.0, 103.0],
            index=pd.bdate_range("2020-01-01", periods=4),
        )
        sig = str(s.index[0].date())
        # fill bar 1 (price 101); H=2 -> bar 3 (price 103)
        assert grading.grade_next_bar_return(s, sig, 2) == pytest.approx(103.0 / 101.0 - 1.0)

    def test_constants_have_expected_values(self):
        """Pre-registered barrier constants must not drift."""
        assert STOP_BARRIER    == pytest.approx(0.95)
        assert CUSHION_BARRIER == pytest.approx(1.05)
        assert LIFTOFF_15      == pytest.approx(1.15)
        assert LIFTOFF_8       == pytest.approx(1.08)
        assert LIFTOFF_HORIZON_126 == 126
        assert LIFTOFF_HORIZON_21  == 21
        assert DEAD_MONEY_BAND == pytest.approx(0.08)
        assert DEAD_MONEY_CAP  == pytest.approx(0.05)
