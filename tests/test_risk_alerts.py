"""Tests for the Phase-2 risk-state alerts + risk_state.core_series.

core_series is unit-tested by injecting a synthetic conditions_frame; the alert
rules are tested for their cross logic with the series/frame stubbed.
"""
from __future__ import annotations

import pandas as pd

from engine import alerts, risk_state as rs


def _cf(rows: list[dict]) -> pd.DataFrame:
    idx = pd.date_range("2026-06-01", periods=len(rows), freq="D")
    return pd.DataFrame(rows, index=idx)


# --- core_series -------------------------------------------------------------
def test_core_series_computes_and_escalates(monkeypatch):
    # row 0 benign; row 1 has 2 hard leading legs (complacency hidden + breadth div)
    cf = _cf([
        {"complacency_calm": 0, "complacency_fragility": 0, "spy_high_prox": 0.90,
         "breadth_above200_pctile": 0.80, "hy_oas_chg_21d": -1.0, "vix_term": 0.85,
         "vrp_pctile": 0.3, "skew_pctile": 0.3},
        {"complacency_calm": 1, "complacency_fragility": 2, "spy_high_prox": 0.99,
         "breadth_above200_pctile": 0.10, "hy_oas_chg_21d": 5.0, "vix_term": 0.85,
         "vrp_pctile": 0.3, "skew_pctile": 0.3},
    ])
    monkeypatch.setattr("engine.conditions.conditions_frame", lambda f: cf)
    s = rs.core_series(pd.DataFrame(index=cf.index))
    assert isinstance(s, pd.Series)
    assert len(s) == 2
    assert s.iloc[0] < s.iloc[1]
    # 2 hot leading legs on row 1 -> floored to at least caution (40)
    assert s.iloc[1] >= 40


def test_core_series_empty_when_no_legs(monkeypatch):
    monkeypatch.setattr("engine.conditions.conditions_frame",
                        lambda f: pd.DataFrame(index=pd.date_range("2026-06-01", periods=2)))
    s = rs.core_series(pd.DataFrame())
    assert s.empty


# --- risk_state_elevated -----------------------------------------------------
def test_risk_state_elevated_fires_on_cross(monkeypatch):
    monkeypatch.setattr(rs, "core_series",
                        lambda f: pd.Series([50.0, 65.0]))
    a = alerts.risk_state_elevated(None, pd.DataFrame())
    assert a is not None and a.rule == "risk_state_elevated"
    assert a.severity == "warn"


def test_risk_state_riskoff_is_act(monkeypatch):
    monkeypatch.setattr(rs, "core_series", lambda f: pd.Series([50.0, 85.0]))
    a = alerts.risk_state_elevated(None, pd.DataFrame())
    assert a is not None and a.severity == "act"


def test_risk_state_no_fire_when_already_elevated(monkeypatch):
    monkeypatch.setattr(rs, "core_series", lambda f: pd.Series([65.0, 66.0]))
    assert alerts.risk_state_elevated(None, pd.DataFrame()) is None


def test_risk_state_no_fire_when_below(monkeypatch):
    monkeypatch.setattr(rs, "core_series", lambda f: pd.Series([30.0, 55.0]))
    assert alerts.risk_state_elevated(None, pd.DataFrame()) is None


# --- hidden_fragility --------------------------------------------------------
def test_hidden_fragility_act_on_strong_cross(monkeypatch):
    cf = _cf([{"complacency_calm": 1, "complacency_fragility": 1},
              {"complacency_calm": 1, "complacency_fragility": 2}])
    monkeypatch.setattr(alerts, "_conditions_frame", lambda f: cf)
    a = alerts.hidden_fragility(None, pd.DataFrame())
    assert a is not None and a.rule == "hidden_fragility" and a.severity == "act"


def test_hidden_fragility_warn_on_watch_cross(monkeypatch):
    cf = _cf([{"complacency_calm": 0, "complacency_fragility": 0},
              {"complacency_calm": 1, "complacency_fragility": 1}])
    monkeypatch.setattr(alerts, "_conditions_frame", lambda f: cf)
    a = alerts.hidden_fragility(None, pd.DataFrame())
    assert a is not None and a.severity == "warn"


def test_hidden_fragility_no_fire_when_unchanged(monkeypatch):
    cf = _cf([{"complacency_calm": 1, "complacency_fragility": 2},
              {"complacency_calm": 1, "complacency_fragility": 2}])
    monkeypatch.setattr(alerts, "_conditions_frame", lambda f: cf)
    assert alerts.hidden_fragility(None, pd.DataFrame()) is None


# --- breadth_divergence ------------------------------------------------------
def test_breadth_divergence_fires_on_cross(monkeypatch):
    cf = _cf([{"spy_high_prox": 0.90, "breadth_above200_pctile": 0.80},
              {"spy_high_prox": 0.99, "breadth_above200_pctile": 0.10}])
    monkeypatch.setattr(alerts, "_conditions_frame", lambda f: cf)
    a = alerts.breadth_divergence(None, pd.DataFrame())
    assert a is not None and a.rule == "breadth_divergence"


def test_breadth_divergence_no_fire_when_confirming(monkeypatch):
    cf = _cf([{"spy_high_prox": 0.90, "breadth_above200_pctile": 0.80},
              {"spy_high_prox": 0.95, "breadth_above200_pctile": 0.70}])
    monkeypatch.setattr(alerts, "_conditions_frame", lambda f: cf)
    assert alerts.breadth_divergence(None, pd.DataFrame()) is None
