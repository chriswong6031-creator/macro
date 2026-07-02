"""Tests for engine.grading — the one honest grader (W1c, audit #15/#46).

Covers the four axes it standardizes:
  1. next-bar fill (entry = bar AFTER the signal; forward window strictly forward of it)
  2. survivorship via as_of_members (the panel changes vs today's survivors)
  3. dual return basis (documented; total-return is the default free basis)
  4. delisting terminal values — a name that dies mid-horizon grades as a LOSS, not vanishing
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import grading


def _series(vals, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series([float(v) for v in vals], index=idx)


# --------------------------------------------------------------------------- #
# 1. NEXT-BAR FILL
# --------------------------------------------------------------------------- #
class TestNextBarFill:
    def test_fill_index_is_signal_bar_plus_one(self):
        s = _series(range(10, 30))            # 20 bars
        sig_date = str(s.index[5].date())
        assert grading.fill_index(s, sig_date) == 6

    def test_fill_index_none_when_no_next_bar(self):
        s = _series(range(10, 30))
        last = str(s.index[-1].date())
        assert grading.fill_index(s, last) is None    # nothing to fill into

    def test_entry_price_is_next_bar_close(self):
        s = _series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
        sig = str(s.index[2].date())          # signal on bar 2 (close 102)
        m = grading.forward_metrics(s, sig, horizons=(3,))
        assert m["entry_price"] == 103.0      # NEXT bar (index 3)
        assert m["fill_offset"] == 1

    def test_forward_return_measured_from_fill(self):
        # entry at fill (bar 3, price 103); +3 bars -> bar 6 price 106
        s = _series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
        sig = str(s.index[2].date())
        m = grading.forward_metrics(s, sig, horizons=(3,))
        assert abs(m["fwd_ret_3"] - (106.0 / 103.0 - 1.0)) < 1e-9

    def test_mdd_window_strictly_forward_of_fill(self):
        # Trough is the ENTRY bar itself — a strictly-forward window must NOT see it as a drawdown.
        s = _series([100, 100, 90, 110, 120, 130, 140])
        sig = str(s.index[1].date())          # signal bar 1 -> fill bar 2 (price 90)
        m = grading.forward_metrics(s, sig, horizons=(3,))
        assert m["entry_price"] == 90.0
        # forward window is bars 3,4,5 (all above 90) -> no drawdown from the 90 fill
        assert m["fwd_mdd_3"] == 0.0

    def test_same_bar_shadow_differs_from_next_bar(self):
        s = _series([100, 90, 95, 105, 110, 120])
        sig = str(s.index[0].date())
        nb = grading.forward_metrics(s, sig, horizons=(3,))
        sb = grading.forward_metrics(s, sig, horizons=(3,), same_bar=True)
        assert nb["entry_price"] == 90.0 and sb["entry_price"] == 100.0
        assert nb["fwd_ret_3"] != sb["fwd_ret_3"]  # the correction is real & measurable

    def test_horizon_not_matured_is_none(self):
        s = _series(range(100, 105))          # only 5 bars
        sig = str(s.index[0].date())
        m = grading.forward_metrics(s, sig, horizons=(60,))
        assert m["fwd_ret_60"] is None


# --------------------------------------------------------------------------- #
# 4. DELISTING TERMINAL VALUES — the loss must be realized, not dropped
# --------------------------------------------------------------------------- #
class TestDelistingTerminal:
    def test_dead_name_graded_as_loss_not_vanished(self):
        # A name whose live cache stops early, extended by an imputed −100% bankruptcy
        # terminal, must grade its horizon as a total loss — never disappear.
        live = _series([100, 100, 100], start="2020-01-01")    # trades 3 days then gone
        # dead store: a −100% terminal AFTER the live series ends
        dead_idx = pd.bdate_range("2020-01-06", periods=2)
        dead = {"ZOMB": pd.Series([50.0, 0.0], index=dead_idx)}  # imputed bankruptcy → 0
        resolved = grading.resolve_series("ZOMB", live, dead_prices=dead)
        # the resolved series must carry the terminal 0.0 (the wipe)
        assert resolved.iloc[-1] == 0.0
        assert len(resolved) == 5

        sig = str(live.index[0].date())        # signal on day 0 -> fill day 1 (price 100)
        m = grading.forward_metrics(resolved, sig, horizons=(3,))
        assert m["entry_price"] == 100.0
        # 3 bars past the fill lands on the imputed 0.0 -> −100% return, graded as the LOSS
        assert m["fwd_ret_3"] == pytest.approx(-1.0)
        assert m["fwd_mdd_3"] == pytest.approx(-1.0)

    def test_resolve_series_no_dead_returns_live(self):
        live = _series([10, 11, 12])
        assert grading.resolve_series("X", live, dead_prices={}).equals(live)

    def test_resolve_series_dead_only_when_no_live(self):
        dead = {"D": _series([5, 4, 0])}
        out = grading.resolve_series("D", None, dead_prices=dead)
        assert out is not None and out.iloc[-1] == 0.0


# --------------------------------------------------------------------------- #
# 2. SURVIVORSHIP — the as-of panel differs from today's survivors
# --------------------------------------------------------------------------- #
class TestSurvivorshipPanel:
    def _ledger(self):
        # A member that DROPPED (last_seen before asof) and one that survived.
        return pd.DataFrame([
            {"ticker": "SURV", "group": "sp500", "name": "Surv", "sector": "Tech",
             "first_seen": pd.Timestamp("2015-01-01"), "last_seen": pd.Timestamp("2026-01-01"),
             "active": True},
            {"ticker": "GONE", "group": "sp500", "name": "Gone", "sector": "Fin",
             "first_seen": pd.Timestamp("2015-01-01"), "last_seen": pd.Timestamp("2017-06-01"),
             "active": False},
        ])

    def test_as_of_members_excludes_names_not_yet_or_no_longer_members(self):
        from engine.universe_history import as_of_members
        led = self._ledger()
        # In 2016 BOTH were members; in 2020 only SURV (GONE dropped 2017-06).
        m2016 = as_of_members("2016-06-01", ledger=led)
        m2020 = as_of_members("2020-06-01", ledger=led)
        assert set(m2016) == {"SURV", "GONE"}
        assert set(m2020) == {"SURV"}
        # PROOF the panel differs: the as-of-2016 universe carries a name today's survivor
        # panel (2020) has erased — the exact survivorship the grader must respect.
        assert "GONE" in m2016 and "GONE" not in m2020

    def test_as_of_panel_reconstructs_2016_universe(self):
        led = self._ledger()
        closes = {
            "SURV": _series(range(10, 400), start="2015-06-01"),
            "GONE": _series(range(20, 60), start="2015-06-01"),
        }
        panel = grading.as_of_panel(closes, "2016-06-01", ledger=led,
                                    include_dead=False)
        assert panel["survivorship"] == "as-of"
        assert set(panel["members"]) == {"SURV", "GONE"}
        assert "GONE" in panel["closes"]      # the dropped name is IN the 2016 panel

    def test_cold_start_falls_back_and_is_flagged(self):
        # asof before accrual (empty ledger) -> cold-start tag + today's panel.
        closes = {"A": _series(range(10, 400))}
        panel = grading.as_of_panel(closes, "2010-01-01", ledger=pd.DataFrame(),
                                    include_dead=False)
        assert panel["survivorship"] == "cold-start"
        assert set(panel["members"]) == {"A"}


# --------------------------------------------------------------------------- #
# 3. DUAL RETURN BASIS — tags exist and are distinct
# --------------------------------------------------------------------------- #
def test_grade_basis_tags():
    assert grading.GradeBasis.TOTAL == "total_return"
    assert grading.GradeBasis.PRICE == "price_return"
    assert grading.GradeBasis.TOTAL != grading.GradeBasis.PRICE


def test_grade_next_bar_return_single_horizon():
    s = _series([100, 101, 102, 103, 104, 105])
    sig = str(s.index[0].date())           # fill bar 1 (101); +2 -> bar 3 (103)
    assert grading.grade_next_bar_return(s, sig, 2) == pytest.approx(103.0 / 101.0 - 1.0)
