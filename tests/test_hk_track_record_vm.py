"""Tests for scripts/build_hk._hk_track_record_vm — the W6 public-scoreboard panel
view-model.

The helper adapts engine.board_ledger.scorecard('HK') into a compact, template-ready
dict for the track-record panel (§7.4 of the HK/Canada masterplan). It must:

  1. Render the honest 'accruing' state with derived dates (accruing-since = the
     ledger's first logged call-date; first 21d read ~ +21 business days; stable
     read = the program-level first_read_est) — never raising.
  2. Emit per-horizon rank-IC + hit-rate rows only in the 'scored' state.
  3. Degrade gracefully (no crash) when the ledger store is absent.

All monkeypatching is against the board_ledger surface; no real render runs.
"""
from __future__ import annotations

import pandas as pd
import pytest

import scripts.build_hk as b
from engine import board_ledger


@pytest.fixture
def _accruing_scorecard(monkeypatch):
    """Patch scorecard() to an accruing dict and the store to a 1-date parquet."""
    def fake_scorecard(market):
        assert market == "HK"
        return {
            "market": "HK", "status": "accruing",
            "n_calls": 9, "n_graded": 0, "n_suspended": 0,
            "survivorship": "no_dead_name_store",
            "first_read_est": "2026-08-24",
            "by_horizon": {}, "note": "accruing",
        }
    monkeypatch.setattr(board_ledger, "scorecard", fake_scorecard)


def test_accruing_shape_and_derived_dates(monkeypatch, tmp_path, _accruing_scorecard):
    # a store whose first date is 2026-07-03 → first_21d_read = +21 business days
    store = tmp_path / "hk_board.parquet"
    pd.DataFrame({"date": ["2026-07-03", "2026-07-03"], "ticker": ["A", "B"]}).to_parquet(store)
    monkeypatch.setattr(board_ledger, "_store_path", lambda m: store)

    vm = b._hk_track_record_vm()
    assert vm is not None
    assert vm["status"] == "accruing"
    assert vm["first_write"] == "2026-07-03"
    # +21 business days from 2026-07-03 (a Friday) lands on 2026-08-03 (a Monday)
    assert vm["first_21d_read"] == "2026-08-03"
    assert vm["first_stable_read"] == "2026-08-24"
    assert vm["n_calls"] == 9
    # accruing state carries NO graded horizons block
    assert "horizons" not in vm


def test_accruing_survives_missing_store(monkeypatch, tmp_path, _accruing_scorecard):
    """No ledger parquet yet → panel still renders; dates are just None."""
    monkeypatch.setattr(board_ledger, "_store_path", lambda m: tmp_path / "nope.parquet")
    vm = b._hk_track_record_vm()
    assert vm is not None
    assert vm["status"] == "accruing"
    assert vm["first_write"] is None
    assert vm["first_21d_read"] is None
    # program-level stable-read date still surfaces
    assert vm["first_stable_read"] == "2026-08-24"


def test_scored_emits_horizon_rows(monkeypatch, tmp_path):
    def fake_scorecard(market):
        return {
            "market": "HK", "status": "scored",
            "n_calls": 120, "n_graded": 90, "n_suspended": 3,
            "survivorship": "no_dead_name_store", "first_read_est": "2026-08-24",
            "by_horizon": {
                "21d": {"n": 90, "rank_ic": -0.041, "n_ic_dates": 6,
                        "hit_rate_21d": 0.58, "n_buy": 40,
                        "by_group": {"entry_open": {"n": 40, "pos_rate": 0.6, "mean_excess": 0.012}}},
                "63d": {"n": 70, "rank_ic": -0.02, "n_ic_dates": 6,
                        "hit_rate_21d": None, "n_buy": 30, "by_group": {}},
            },
            "note": "scored",
        }
    monkeypatch.setattr(board_ledger, "scorecard", fake_scorecard)
    store = tmp_path / "hk_board.parquet"
    pd.DataFrame({"date": ["2026-07-03"], "ticker": ["A"]}).to_parquet(store)
    monkeypatch.setattr(board_ledger, "_store_path", lambda m: store)

    vm = b._hk_track_record_vm()
    assert vm["status"] == "scored"
    assert "horizons" in vm and len(vm["horizons"]) == 2
    h21 = next(h for h in vm["horizons"] if h["h"] == "21d")
    assert h21["rank_ic"] == -0.041
    assert h21["hit_rate_21d"] == 0.58
    assert h21["by_group"][0]["group"] == "entry_open"
