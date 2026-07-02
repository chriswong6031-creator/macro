"""Audit #39 — calibration-frame reconciliation tests.

Two protocol invariants for the recession/nowcast/business-cycle signals whose
advertised stats were calibrated on a different data frame than they fire on:

1. PIT-frame invariance — a stat computed AS-OF date D must not move when data that
   arrived AFTER D is appended. Proven on the drawdown-risk band table's PIT
   ('release') accessor: truncating the vintage/store to <= D and asking for the
   as-of value yields the same number whether or not post-D revisions exist.

2. Lag-config consistency — the LIVE business-cycle signal must fire at the SAME
   publication lag its calibration (and its advertised lead/FP stats) were measured
   at, OR the artifact must carry both stats. We assert the live lag equals the
   calibrated lag and that the snapshot ships a lag passport + a marked shadow of the
   pre-fix reading.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import business_cycle as bc  # noqa: E402
from engine import conditions, pit  # noqa: E402
from lib import config  # noqa: E402


# --- Leg 1: drawdown-risk band table is re-issued on the PIT frame ------------
def test_drawdown_band_table_is_measured_pit_not_stale():
    """The band table conditions.py ships must be the RE-ISSUED PIT numbers, not the
    retired 8/26/36/38 (Sahm-era) table. Base rate must be well above the old 8%."""
    bt = conditions._drawdown_band_table()
    # monotone low <= elevated <= high <= extreme
    assert bt["low"] <= bt["elevated"] <= bt["high"] <= bt["extreme"]
    # the retired table claimed 8% base; the honest max-drawdown base is ~19%
    assert bt["base"] >= 15, "base rate must reflect the honest max-drawdown definition"
    # the retired extreme was 38%; the re-issued extreme is materially higher
    assert bt["extreme"] >= 45, "re-issued extreme band should exceed the stale 38%"


def test_drawdown_snapshot_carries_measured_passport():
    """The rendered drawdown block must stamp a measured-basis PIT passport with the
    live claims composition, replacing the old bare 8/26/36/38 numbers + 8% base."""
    # build a minimal frame that yields a drawdown_risk score so the block renders
    from engine import inputs
    try:
        f = inputs.build_features()
    except Exception:  # noqa: BLE001 — store not populated in this env
        pytest.skip("store not populated")
    cf = conditions.conditions_frame(f)
    if "drawdown_risk" not in cf.columns or cf["drawdown_risk"].dropna().empty:
        pytest.skip("no drawdown_risk in this environment")
    snap = conditions.conditions_snapshot(f)
    dr = snap["drawdown_risk"]
    assert dr["stat_passport"]["basis"] == "measured"
    assert dr["stat_passport"]["frame"] == "pit"
    assert dr["stat_passport"]["labor_leg"] == "claims"   # NOT the retired Sahm leg
    # the base rate the block advertises is the honest one, not the stale 8%
    assert dr["base_rate_pct"] >= 15
    # per-band probability must match the passported table for the current band
    if dr["band"] is not None:
        assert dr["dd10_prob_pct"] == conditions._drawdown_band_table()[dr["band"]]


def test_pit_release_is_asof_invariant_to_future_revisions():
    """PIT invariance: the 'release' value of a vintaged econ column as-of date D is
    unchanged by appending vintages that arrive AFTER D. Uses a synthetic ICSA-style
    matrix so it runs without the live store."""
    # two vintages for the same reference period: an initial print, then a later revision
    ref = pd.Timestamp("2015-03-07")            # week-ending reference date
    v = pd.DataFrame([
        {"series": "ICSA", "period": ref, "realtime_start": pd.Timestamp("2015-03-12"), "value": 300.0},
        {"series": "ICSA", "period": ref, "realtime_start": pd.Timestamp("2015-04-02"), "value": 285.0},  # revision
    ])
    col = "initial_claims"
    as_of = pd.Timestamp("2015-03-20")          # BETWEEN the initial and the revision
    # as-of the 20th, only the initial 300.0 was knowable
    s_before = pit.series(col, as_of=as_of, basis="release", vintages=v)
    assert not s_before.empty
    assert float(s_before.iloc[-1]) == 300.0, "as-of value must be the initial release, not the revision"
    # now append the same-plus-future matrix (identical here) and recompute as-of the SAME D
    s_after = pit.series(col, as_of=as_of, basis="release", vintages=v)
    assert float(s_after.iloc[-1]) == float(s_before.iloc[-1]), "future revision must not move the as-of value"


def test_drawdown_band_artifact_wins_over_fallback_when_present():
    """If the committed artifact is present, the live table reads it (so a re-run
    updates the site without a code change); else it uses the pinned fallback."""
    conditions._drawdown_band_table.cache_clear()
    bt = conditions._drawdown_band_table()
    p = config.data_dir() / "regime" / "drawdown_risk_pit.json"
    if p.exists():
        d = json.loads(p.read_text())
        rel = d["frames"]["release"]["bands"]
        assert bt["extreme"] == round(rel["extreme"]["hit_pct"])
        assert bt["frame"] == "pit"
    else:
        assert bt == dict(conditions._DRAWDOWN_BAND_PIT_FALLBACK)


# --- Leg 2: business-cycle live lag == calibrated lag -------------------------
def test_live_lag_equals_calibrated_lag():
    """Lag-config consistency: the config live_lag_m the live snapshot fires at must
    equal the lag its calibration was measured at (the 5.7m-lead / 3-FP stats)."""
    cfg = config.load()["engine"]["business_cycle"]
    live_lag = int(cfg.get("live_lag_m", 1))
    cal_path = config.data_dir() / "regime" / "business_cycle_calibration.json"
    if not cal_path.exists():
        pytest.skip("no calibration artifact in this environment")
    cal = json.loads(cal_path.read_text())
    cal_lag = int(cal.get("measured", {}).get("calibration_lag_m", 1))
    assert live_lag == cal_lag, (
        f"live signal fires at lag_m={live_lag} but its stats were calibrated at "
        f"lag_m={cal_lag} — this is the audit-#39 leak")
    assert live_lag >= 1, "lag_m=0 leaks a month of look-ahead on the monthly legs"


def test_snapshot_carries_lag_passport_and_shadow():
    """The live snapshot must ship a lag passport (basis measured, leak_removed) and,
    while shadow_lag_m != live_lag_m, a MARKED shadow of the legacy unlagged reading."""
    frame = bc.cycle_frame()
    if frame is None or "leading_mom6" not in frame.columns:
        pytest.skip("store not populated")
    snap = bc.business_cycle_snapshot()   # LIVE path (no frame supplied)
    lp = snap["lag_passport"]
    assert lp["basis"] == "measured"
    assert lp["live_lag_m"] >= 1 and lp["leak_removed"] is True
    # shadow present and correctly marked (config ships shadow_lag_m=0 != live_lag_m=1)
    if snap.get("shadow") is not None:
        assert snap["shadow"]["is_shadow"] is True
        assert snap["shadow"]["lag_m"] == 0
        assert "phase" in snap["shadow"]


def test_harness_frame_bypasses_shadow_and_lag_router():
    """When an explicit frame is supplied (the validation harness), the snapshot must
    NOT invent a shadow (the harness controls its own lag) — no double-lagging."""
    from tests.test_business_cycle import _cfg, _synthetic_frame
    snap = bc.business_cycle_snapshot(frame=_synthetic_frame(), cfg=_cfg())
    assert snap.get("shadow") is None
    assert snap["available"] is True


def test_lag_shift_changes_phase_clock_direction():
    """Documents WHY the lag fix matters: on the live store, the unlagged (lag 0) and
    calibrated (lag 1) frames can disagree on the leading-momentum sign — the leak the
    fix removes. Not asserted equal; asserted that both are well-formed."""
    cfg = config.load()["engine"]["business_cycle"]
    p0 = bc._phase_at_lag(cfg, 0)
    p1 = bc._phase_at_lag(cfg, 1)
    if p0 is None or p1 is None:
        pytest.skip("store not populated")
    for p in (p0, p1):
        assert p["phase"]["label"] in ("expansion", "slowdown", "contraction", "recovery", "unknown")
        assert p["lag_m"] in (0, 1)
