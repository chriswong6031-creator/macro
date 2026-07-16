"""Hermetic tests for T6 config-ization — the frozen pre-registration seeds are the
default, an optional `momentum_king:` config block overrides them, and the params
passport echoes the thresholds that ACTUALLY ran. No Bash, no network.
"""
import pandas as pd

from engine.momentum_king import (
    ALPHA_LEADER_MIN,
    DOMINANCE_TAU,
    FRESH_WITHIN,
    build_board,
)


def test_mk_config_defaults_to_frozen_seeds(monkeypatch):
    import scripts.build_momentum_king as bmk
    monkeypatch.setattr(bmk.config, "load", lambda: {})           # no momentum_king block
    c = bmk._mk_config()
    assert c["alpha_leader_min"] == ALPHA_LEADER_MIN
    assert c["dominance_tau"] == DOMINANCE_TAU
    assert c["fresh_within"] == FRESH_WITHIN
    assert c["theme_min_members"] == bmk._THEME_MIN_MEMBERS
    assert c["max_groups"] == bmk._MAX_GROUPS


def test_mk_config_override_flows_through(monkeypatch):
    import scripts.build_momentum_king as bmk
    monkeypatch.setattr(bmk.config, "load", lambda: {"momentum_king": {
        "dominance_tau": 0.9, "fresh_within": 7, "sub_min_members": 8}})
    c = bmk._mk_config()
    assert c["dominance_tau"] == 0.9 and c["fresh_within"] == 7 and c["sub_min_members"] == 8
    # untouched keys keep the frozen seed
    assert c["alpha_leader_min"] == ALPHA_LEADER_MIN


def test_mk_config_absent_safe(monkeypatch):
    import scripts.build_momentum_king as bmk

    def _boom():
        raise RuntimeError("config unavailable")

    monkeypatch.setattr(bmk.config, "load", _boom)
    c = bmk._mk_config()                                          # must fall back, not raise
    assert c["dominance_tau"] == DOMINANCE_TAU


def test_build_board_params_echo_threaded_thresholds():
    # the params passport echoes the ACTUAL thresholds used, incl. fresh_within/extended_atr
    residual = {"as_of": "2026-07-10", "by_sector": {"IT": {"n": 5, "leaders": [
        {"ticker": "AAA", "name": "AAA", "sector": "IT", "alpha": 2.0, "entry": "intact",
         "sector_rank": 1, "sector_n": 5, "rev_pctile": 40}]}}}
    board = build_board(residual, pd.DataFrame(),
                        dominance_tau=0.9, fresh_within=7, extended_atr=9.0)
    p = board["params"]
    assert p["dominance_tau"] == 0.9 and p["fresh_within"] == 7 and p["extended_atr"] == 9.0
