"""engine/market_state_tune.py — bounded, do-no-harm auto-calibration of corroborator weights."""
from __future__ import annotations

from pathlib import Path

import engine.market_state as M
import engine.market_state_audit as A
import engine.market_state_tune as T


def _row(asof, dd, keys, state="caution", sev=True, verdict="RISK_OFF", raw=61):
    return {"asof": asof, "verdict": verdict, "raw_score": raw, "radar_state": state,
            "amp": len(keys), "amp_keys": keys, "severe_gated": sev,
            "graded": {"any_dd5_within_h21": dd, "fwd_dd": {"h21": -0.06 if dd else 0.0}}}


def _seed(root, n_tp=12, n_fp=8, n_calm=5):
    rows = [_row(f"2026-02-{i+1:02d}", True, ["conjunction", "two_plus_scares", "complacency"])
            for i in range(n_tp)]
    rows += [_row(f"2026-03-{i+1:02d}", False, ["drawdown_band", "systemic_stress"])
             for i in range(n_fp)]
    rows += [_row(f"2026-04-{i+1:02d}", False, [], state="calm", sev=False, verdict="RISK_ON")
             for i in range(n_calm)]
    A._write(A._path(root), rows)


def test_default_calib_reproduces_flat_six(tmp_path):
    c = M._ms_calib(root=tmp_path)               # no file -> defaults
    assert c["weights"] == {k: 6.0 for k in M.CORROBORATORS}
    # the canonical today case: caution + severe + 3 corroborators -> ceiling 28
    assert M._ceiling_for("caution", True, ["conjunction", "two_plus_scares", "complacency"], c) == 28
    assert M._ceiling_for("caution", False, [], c) == 56
    assert M._ceiling_for("calm", False, [], c) is None


def test_gated_until_enough_graded(tmp_path):
    _seed(tmp_path, n_tp=3, n_fp=2, n_calm=2)     # 7 < MIN_GRADED
    r = T.tune(root=tmp_path)
    assert r["status"] == "accruing" and r["need"] == T.MIN_GRADED
    assert not (Path(T._calib_path(tmp_path)).exists())


def test_corr_lift_separates_signal_from_noise(tmp_path):
    _seed(tmp_path)
    lift, base = T._corr_lift(T._graded(tmp_path))
    assert lift["conjunction"]["lift"] > 1.5         # led every drawdown
    assert lift["drawdown_band"]["lift"] == 0.0      # never preceded one


def test_converges_prunes_noise_and_holds(tmp_path):
    _seed(tmp_path)
    last = None
    for _ in range(6):
        last = T.tune(root=tmp_path)
        # INVARIANT: an applied step never regresses F1 and never adds false positives
        if last["status"] == "apply":
            bt = last["backtest"]
            assert bt["candidate"]["f1"] >= bt["current"]["f1"]
            assert bt["candidate"]["fp"] <= bt["current"]["fp"]
    w = M._ms_calib(root=tmp_path)["weights"]
    assert w["conjunction"] >= 9.0 and w["complacency"] >= 9.0     # up-weighted
    assert w["drawdown_band"] == 0.0 and w["systemic_stress"] == 0.0   # pruned
    assert last["status"] == "hold"                  # converged -> stops changing
    # the converged weights eliminate the false positives entirely
    assert T._backtest(T._graded(tmp_path), M._ms_calib(root=tmp_path))["fp"] == 0


def test_weights_stay_in_bounds(tmp_path):
    _seed(tmp_path, n_tp=25, n_fp=2, n_calm=2)       # extreme lift on the winners
    for _ in range(8):
        T.tune(root=tmp_path)
    for v in M._ms_calib(root=tmp_path)["weights"].values():
        assert M._WEIGHT_BOUNDS[0] <= v <= M._WEIGHT_BOUNDS[1]
